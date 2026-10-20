import uuid
from datetime import UTC, date, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events import espn, service
from app.events.errors import EventNotFoundError, InvalidImportWindowError
from app.events.models import Event
from app.events.schema import EventStatus, League
from tests.events.conftest import NBA_DAY, NFL_DAY, FakeEspn, event_with_status

pytestmark = pytest.mark.anyio

LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


async def import_both(db: AsyncSession, schedule: espn.EspnSchedule) -> None:
    await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    await service.import_schedule(db, schedule, League.NBA, NBA_DAY, 1)


async def count_events(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Event))).scalar_one()


async def test_import_stores_every_event(db: AsyncSession, schedule: espn.EspnSchedule) -> None:
    summary = await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    assert (summary.fetched, summary.created, summary.updated) == (12, 12, 0)
    assert await count_events(db) == 12


async def test_import_walks_each_day_of_the_window(
    db: AsyncSession, schedule: espn.EspnSchedule, fake_espn: FakeEspn
) -> None:
    summary = await service.import_schedule(
        db, schedule, League.NFL, NFL_DAY - timedelta(days=2), 5
    )
    asked_for = [request.url.params["dates"] for request in fake_espn.requests]
    assert asked_for == ["20261016", "20261017", "20261018", "20261019", "20261020"]
    assert summary.fetched == 12  # only the 18th has games in the recordings


async def test_reimport_updates_instead_of_duplicating(
    db: AsyncSession, schedule: espn.EspnSchedule, fake_espn: FakeEspn
) -> None:
    await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    again = await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    assert (again.created, again.updated) == (0, 12)
    assert await count_events(db) == 12


async def test_reimport_picks_up_changes(
    db: AsyncSession, schedule: espn.EspnSchedule, fake_espn: FakeEspn
) -> None:
    """A game that has started is updated in place, not added again."""
    await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    fake_espn.override = lambda _: httpx2.Response(
        200, content=event_with_status("STATUS_IN_PROGRESS", "in")
    )
    summary = await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    stored = (
        await db.execute(select(Event).where(Event.source_event_id == "401872996"))
    ).scalar_one()
    assert (summary.created, summary.updated) == (0, 1)
    assert stored.status == EventStatus.LIVE
    assert await count_events(db) == 12


async def test_empty_window_stores_nothing(db: AsyncSession, schedule: espn.EspnSchedule) -> None:
    summary = await service.import_schedule(db, schedule, League.NFL, date(2026, 7, 1), 3)
    assert (summary.fetched, summary.created, summary.updated) == (0, 0, 0)


@pytest.mark.parametrize("days", [0, -1, 32], ids=["zero", "negative", "over-31"])
async def test_import_window_is_bounded(
    db: AsyncSession, schedule: espn.EspnSchedule, fake_espn: FakeEspn, days: int
) -> None:
    with pytest.raises(InvalidImportWindowError):
        await service.import_schedule(db, schedule, League.NFL, NFL_DAY, days)
    assert fake_espn.requests == []  # refused before anything is fetched


async def test_list_is_in_start_order(db: AsyncSession, schedule: espn.EspnSchedule) -> None:
    await import_both(db, schedule)
    events = await service.list_events(db, league=None, starts_after=LONG_AGO, limit=100, offset=0)
    starts = [event.starts_at for event in events]
    assert len(events) == 14
    assert starts == sorted(starts)


@pytest.mark.parametrize(
    ("league", "expected"), [(League.NFL, 12), (League.NBA, 2)], ids=["nfl", "nba"]
)
async def test_list_filters_by_league(
    db: AsyncSession, schedule: espn.EspnSchedule, league: League, expected: int
) -> None:
    await import_both(db, schedule)
    events = await service.list_events(
        db, league=league, starts_after=LONG_AGO, limit=100, offset=0
    )
    assert len(events) == expected
    assert {event.league for event in events} == {league}


async def test_list_skips_events_before_starts_after(
    db: AsyncSession, schedule: espn.EspnSchedule
) -> None:
    await import_both(db, schedule)
    events = await service.list_events(
        db, league=None, starts_after=datetime(2026, 10, 20, tzinfo=UTC), limit=100, offset=0
    )
    assert {event.league for event in events} == {"nba"}


async def test_list_defaults_to_recent_and_upcoming(
    db: AsyncSession, schedule: espn.EspnSchedule
) -> None:
    """With no start given, only events from a few hours ago onward are listed."""
    await import_both(db, schedule)
    events = await service.list_events(db, league=None, starts_after=None, limit=100, offset=0)
    cutoff = datetime.now(UTC) - service.LIVE_LOOKBACK
    assert all(event.starts_at.replace(tzinfo=UTC) >= cutoff for event in events)


async def test_list_pages_without_overlap(db: AsyncSession, schedule: espn.EspnSchedule) -> None:
    await import_both(db, schedule)
    pages = [
        await service.list_events(db, league=None, starts_after=LONG_AGO, limit=5, offset=offset)
        for offset in (0, 5, 10)
    ]
    ids = [event.id for page in pages for event in page]
    assert [len(page) for page in pages] == [5, 5, 4]
    assert len(set(ids)) == 14


async def test_get_event(db: AsyncSession, schedule: espn.EspnSchedule) -> None:
    await import_both(db, schedule)
    [listed] = await service.list_events(
        db, league=League.NBA, starts_after=LONG_AGO, limit=1, offset=0
    )
    fetched = await service.get_event(db, listed.id)
    assert fetched.title == listed.title


async def test_get_missing_event_raises(db: AsyncSession) -> None:
    with pytest.raises(EventNotFoundError):
        await service.get_event(db, uuid.uuid4())


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 18, 12, 0, tzinfo=UTC), set()),
        (datetime(2026, 10, 18, 13, 0, tzinfo=UTC), {League.NFL}),
        (datetime(2026, 10, 19, 0, 0, tzinfo=UTC), {League.NFL}),
        (datetime(2026, 10, 19, 6, 0, tzinfo=UTC), set()),
        (datetime(2026, 10, 22, 23, 0, tzinfo=UTC), {League.NBA}),
    ],
    ids=["before-the-window", "30-min-before-kickoff", "late-game-on", "all-over", "nba-night"],
)
async def test_active_leagues_follow_kickoff_times(
    db: AsyncSession, schedule: espn.EspnSchedule, now: datetime, expected: set[League]
) -> None:
    await import_both(db, schedule)
    assert await service.active_leagues(db, now) == expected


@pytest.mark.parametrize(
    ("hours_since_start", "is_active"), [(8, True), (13, False)], ids=["overtime", "stale"]
)
async def test_a_game_still_marked_live_stays_active_for_a_while(
    db: AsyncSession,
    schedule: espn.EspnSchedule,
    fake_espn: FakeEspn,
    hours_since_start: int,
    is_active: bool,
) -> None:
    fake_espn.override = lambda _: httpx2.Response(
        200, content=event_with_status("STATUS_IN_PROGRESS", "in")
    )
    await service.import_schedule(db, schedule, League.NFL, NFL_DAY, 1)
    kickoff = datetime(2026, 10, 18, 13, 30, tzinfo=UTC)  # the recording's first game
    now = kickoff + timedelta(hours=hours_since_start)
    assert (League.NFL in await service.active_leagues(db, now)) is is_active
