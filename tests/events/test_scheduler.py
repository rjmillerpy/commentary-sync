import asyncio
import logging
import os
import signal
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.common.config import Settings
from app.common.db import create_database_engine
from app.events import espn, scheduler
from app.events.models import Event
from app.events.scheduler import ImportJob, SchedulerState, plan_cycle
from app.events.schema import EventStatus, League
from app.streams import service as streams
from app.streams.models import Stream
from app.streams.recorder import create_recorder
from app.streams.schema import GoLive
from tests.conftest import LogLines
from tests.events.conftest import FakeEspn
from tests.streams.conftest import (
    STOP,
    TEST_HLS_BASE_URL,
    TEST_LIVEKIT_API_URL,
    FakeEgress,
    add_commentator,
    add_event,
)

# Sunday morning before the 2026-10-18 NFL games; the NBA recording is the 22nd.
SUNDAY_MORNING = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
DURING_EARLY_GAMES = datetime(2026, 10, 18, 17, 10, tzinfo=UTC)
SATURDAY = date(2026, 10, 17)
SIX_HOURS = timedelta(hours=6)


def requested(fake_espn: FakeEspn) -> list[tuple[str, str]]:
    return [
        (request.url.path.split("/")[-2], request.url.params["dates"])
        for request in fake_espn.requests
    ]


@pytest.fixture
async def engine(migrated_settings: Settings) -> AsyncIterator[AsyncEngine]:
    database = create_database_engine(migrated_settings)
    yield database
    await database.dispose()


async def count_events(engine: AsyncEngine) -> int:
    async with AsyncSession(engine) as db:
        return (await db.execute(select(func.count()).select_from(Event))).scalar_one()


async def live_stream_on_final_event(db: AsyncSession) -> uuid.UUID:
    """A stream someone forgot to end, on a game that has finished."""
    event = await add_event(db, source_id="final-game")
    user = await add_commentator(db)
    stream = await streams.go_live(db, user, GoLive(event_id=event.id), now=SUNDAY_MORNING)
    event.status = EventStatus.FINAL
    await db.commit()
    return stream.id


class TestPlanCycle:
    def test_first_cycle_is_a_full_import_of_every_league(self, settings: Settings) -> None:
        jobs, is_full = plan_cycle(settings, SchedulerState(), SUNDAY_MORNING, active=set())
        assert is_full
        assert jobs == [ImportJob(League.NFL, SATURDAY, 8), ImportJob(League.NBA, SATURDAY, 8)]

    @pytest.mark.parametrize(
        ("since_full", "active", "expected"),
        [
            (timedelta(hours=1), set(), []),
            (timedelta(hours=1), {League.NFL}, [ImportJob(League.NFL, SATURDAY, 2)]),
            (
                timedelta(hours=1),
                {League.NFL, League.NBA},
                [ImportJob(League.NBA, SATURDAY, 2), ImportJob(League.NFL, SATURDAY, 2)],
            ),
        ],
        ids=["nothing-on", "nfl-on", "both-on"],
    )
    def test_between_full_imports_only_active_leagues_refresh(
        self,
        settings: Settings,
        since_full: timedelta,
        active: set[League],
        expected: list[ImportJob],
    ) -> None:
        state = SchedulerState(last_full_import_at=SUNDAY_MORNING - since_full)
        jobs, is_full = plan_cycle(settings, state, SUNDAY_MORNING, active)
        assert (jobs, is_full) == (expected, False)

    @pytest.mark.parametrize(
        "since_full", [SIX_HOURS, SIX_HOURS + timedelta(minutes=1)], ids=["exactly", "overdue"]
    )
    def test_full_import_comes_round_again(self, settings: Settings, since_full: timedelta) -> None:
        state = SchedulerState(last_full_import_at=SUNDAY_MORNING - since_full)
        _, is_full = plan_cycle(settings, state, SUNDAY_MORNING, active={League.NFL})
        assert is_full


@pytest.mark.anyio
class TestRunCycle:
    async def test_full_cycle_imports_the_coming_week(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
    ) -> None:
        state = await scheduler.run_cycle(
            settings, engine, schedule, SchedulerState(), SUNDAY_MORNING
        )
        assert state.last_full_import_at == SUNDAY_MORNING
        assert len(fake_espn.requests) == 16  # 2 leagues x 8 days
        assert await count_events(engine) == 14

    async def test_live_cycle_refreshes_only_the_league_that_is_on(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
    ) -> None:
        state = await scheduler.run_cycle(
            settings, engine, schedule, SchedulerState(), SUNDAY_MORNING
        )
        fake_espn.requests.clear()
        after = await scheduler.run_cycle(settings, engine, schedule, state, DURING_EARLY_GAMES)
        assert requested(fake_espn) == [("nfl", "20261017"), ("nfl", "20261018")]
        assert after == state  # a live cycle doesn't move the full-import clock

    async def test_quiet_cycle_makes_no_requests(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
    ) -> None:
        state = await scheduler.run_cycle(
            settings, engine, schedule, SchedulerState(), SUNDAY_MORNING
        )
        fake_espn.requests.clear()
        # 12:15: the first game (13:30, London) is still more than 30 minutes away.
        await scheduler.run_cycle(
            settings, engine, schedule, state, SUNDAY_MORNING + timedelta(minutes=15)
        )
        assert fake_espn.requests == []

    async def test_one_league_failing_does_not_stop_the_other(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def nba_is_down(request: httpx2.Request) -> httpx2.Response:
            if "basketball" in request.url.path:
                return httpx2.Response(404)
            fake_espn.override = None
            response = fake_espn.handle(request)
            fake_espn.requests.pop()  # handle() recorded it a second time
            fake_espn.override = nba_is_down
            return response

        fake_espn.override = nba_is_down
        with caplog.at_level(logging.ERROR, logger="app.events.scheduler"):
            state = await scheduler.run_cycle(
                settings, engine, schedule, SchedulerState(), SUNDAY_MORNING
            )
        assert await count_events(engine) == 12  # every NFL game
        assert "nba import from 2026-10-17 failed" in caplog.text
        assert state.last_full_import_at is None  # so the next cycle tries the full import again

    async def test_streams_on_finished_games_are_ended(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        db: AsyncSession,
    ) -> None:
        stream_id = await live_stream_on_final_event(db)
        await scheduler.run_cycle(settings, engine, schedule, SchedulerState(), SUNDAY_MORNING)
        db.expunge_all()
        stream = await streams.get_stream(db, stream_id)
        assert stream.ended_at is not None

    async def test_ended_streams_stop_their_recordings(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        db: AsyncSession,
    ) -> None:
        fake_egress = FakeEgress()
        hls = settings.model_copy(
            update={
                "livekit_api_url": HttpUrl(TEST_LIVEKIT_API_URL),
                "hls_base_url": HttpUrl(TEST_HLS_BASE_URL),
            }
        )
        recorder = create_recorder(hls, httpx2.MockTransport(fake_egress.handle))
        stream_id = await live_stream_on_final_event(db)
        await db.execute(update(Stream).values(recording_id="EG_game"))
        await db.commit()
        await scheduler.run_cycle(
            settings, engine, schedule, SchedulerState(), SUNDAY_MORNING, recorder
        )
        assert fake_egress.calls(STOP) == [{"egress_id": "EG_game"}]
        db.expunge_all()
        assert (await streams.get_stream(db, stream_id)).ended_at is not None

    async def test_a_failed_stream_sweep_is_logged_and_retried_next_cycle(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE streams"))
        with caplog.at_level(logging.ERROR, logger="app.events.scheduler"):
            state = await scheduler.run_cycle(
                settings, engine, schedule, SchedulerState(), SUNDAY_MORNING
            )
        assert "could not end abandoned streams" in caplog.text
        assert state.last_full_import_at == SUNDAY_MORNING  # the imports still count

    async def test_database_outage_skips_the_cycle(
        self,
        settings: Settings,
        unreachable_engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.ERROR, logger="app.events.scheduler"):
            state = await scheduler.run_cycle(
                settings, unreachable_engine, schedule, SchedulerState(), SUNDAY_MORNING
            )
        assert state == SchedulerState()
        assert fake_espn.requests == []
        assert "could not read active leagues" in caplog.text


@pytest.mark.anyio
class TestRunForever:
    async def test_cycles_until_stopped_and_writes_a_heartbeat(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
        tmp_path: Path,
    ) -> None:
        # Bypasses the 60 s minimum so the loop turns over quickly in a test.
        fast = settings.model_copy(update={"event_live_import_interval_seconds": 0.01})
        stop = asyncio.Event()
        times = iter([SUNDAY_MORNING, DURING_EARLY_GAMES, DURING_EARLY_GAMES])

        def clock() -> datetime:
            moment = next(times)
            if moment is DURING_EARLY_GAMES:
                stop.set()  # the third cycle never starts
            return moment

        heartbeat = tmp_path / "heartbeat"
        await scheduler.run_forever(fast, engine, schedule, stop, clock, heartbeat)
        assert len(fake_espn.requests) == 16 + 2  # one full cycle, then one live cycle
        assert heartbeat.exists()

    async def test_does_nothing_once_stopped(
        self,
        settings: Settings,
        engine: AsyncEngine,
        schedule: espn.EspnSchedule,
        fake_espn: FakeEspn,
        tmp_path: Path,
    ) -> None:
        stop = asyncio.Event()
        stop.set()
        await scheduler.run_forever(settings, engine, schedule, stop, heartbeat=tmp_path / "hb")
        assert fake_espn.requests == []


class TestMain:
    def test_once_runs_a_full_cycle_and_exits(
        self,
        migrated_settings: Settings,
        http_client_factory: Callable[[float], httpx2.AsyncClient],
        fake_espn: FakeEspn,
    ) -> None:
        assert scheduler.main(["--once"], http_client_factory=http_client_factory) == 0
        assert len(fake_espn.requests) == 2 * 8

    def test_sigterm_stops_the_loop(
        self,
        migrated_settings: Settings,
        http_client_factory: Callable[[float], httpx2.AsyncClient],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """What `docker stop` does: the scheduler finishes its cycle and exits cleanly."""
        monkeypatch.setattr(scheduler, "HEARTBEAT_FILE", tmp_path / "heartbeat")

        def factory(timeout_seconds: float) -> httpx2.AsyncClient:
            asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
            return http_client_factory(timeout_seconds)

        with caplog.at_level(logging.INFO, logger="app.events.scheduler"):
            assert scheduler.main([], http_client_factory=factory) == 0
        assert "scheduler: stopped" in caplog.text


def test_rejects_unknown_arguments(
    http_client_factory: Callable[[float], httpx2.AsyncClient],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        scheduler.main(["--forever"], http_client_factory=http_client_factory)
    assert exit_info.value.code == 2


@pytest.mark.anyio
async def test_each_import_logs_its_numbers_as_fields(
    settings: Settings,
    engine: AsyncEngine,
    schedule: espn.EspnSchedule,
    log_lines: LogLines,
) -> None:
    await scheduler.run_cycle(settings, engine, schedule, SchedulerState(), SUNDAY_MORNING)
    imports = {
        line["import"]["league"]: line["import"]  # type: ignore[index]
        for line in log_lines()
        if "import" in line
    }
    assert set(imports) == {"nfl", "nba"}
    assert imports["nfl"] == {
        "league": "nfl",
        "first_day": "2026-10-17",
        "days": 8,
        "fetched": 12,  # the recorded NFL Sunday
        "created": 12,
        "updated": 0,
    }
