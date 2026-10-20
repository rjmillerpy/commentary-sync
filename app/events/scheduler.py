"""Keep the events table current without anyone running the import by hand.

    python -m app.events.scheduler          # run until SIGTERM (the compose `scheduler` service)
    python -m app.events.scheduler --once   # one cycle, then exit (cron-style)

Every cycle starts from yesterday (UTC), because a late game belongs to the
previous day in ESPN's calendar. A cycle is one of two kinds:

- full: when `event_full_import_interval_seconds` have passed since the last
  one (and on start), every league for yesterday plus `event_import_days`,
  which picks up new games and changed start times or networks;
- live: otherwise, only leagues with a game on now (service.active_leagues),
  for yesterday and today, so statuses move to live and final within one
  `event_live_import_interval_seconds`.

After the imports, every cycle ends abandoned streams: those on events that
are now over, and those whose commentator's audio has been gone longer than
`stream_audio_grace_seconds` (streams.service.end_abandoned_streams), and
stops their HLS recordings.

Run one scheduler per database: two would import the same games twice. Their
writes are idempotent, so that wastes requests but corrupts nothing.
"""

import argparse
import asyncio
import logging
import signal
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.common.config import Settings
from app.common.db import create_database_engine
from app.common.logs import configure_logging
from app.events import espn, service
from app.events.errors import EventsError
from app.events.schema import League
from app.streams import service as streams
from app.streams.recorder import Recorder, create_recorder

# Named, not __name__: run with `python -m` that is "__main__", which is
# outside `app` and so held to warnings (app.common.logs).
logger = logging.getLogger("app.events.scheduler")

# Touched after every cycle; the compose healthcheck reads its age. /tmp is the
# container's private tmpfs (compose.yaml), the only writable path it has.
HEARTBEAT_FILE = Path("/tmp/events-scheduler-heartbeat")  # noqa: S108  # nosec B108
LIVE_WINDOW_DAYS = 2  # yesterday and today
EXIT_OK = 0

HttpClientFactory = Callable[[float], httpx2.AsyncClient]


@dataclass(frozen=True, slots=True)
class ImportJob:
    league: League
    first_day: date
    days: int


@dataclass(frozen=True, slots=True)
class SchedulerState:
    last_full_import_at: datetime | None = None


def plan_cycle(
    settings: Settings, state: SchedulerState, now: datetime, active: set[League]
) -> tuple[list[ImportJob], bool]:
    """What this cycle imports, and whether it is a full cycle. No I/O, so it is easy to test."""
    yesterday = (now - timedelta(days=1)).date()
    full_interval = timedelta(seconds=settings.event_full_import_interval_seconds)
    last_full = state.last_full_import_at
    is_full_due = last_full is None or now - last_full >= full_interval
    if is_full_due:
        days = settings.event_import_days + 1
        return [ImportJob(league, yesterday, days) for league in League], True
    return [ImportJob(league, yesterday, LIVE_WINDOW_DAYS) for league in sorted(active)], False


async def run_cycle(
    settings: Settings,
    engine: AsyncEngine,
    source: service.ScheduleSource,
    state: SchedulerState,
    now: datetime,
    recorder: Recorder | None = None,
) -> SchedulerState:
    """Plan and run one cycle. A failure is logged and skipped, never fatal:
    the next cycle is the retry."""
    try:
        async with AsyncSession(engine) as db:
            active = await service.active_leagues(db, now)
    except SQLAlchemyError:
        logger.exception("scheduler: could not read active leagues; skipping this cycle")
        return state

    jobs, is_full = plan_cycle(settings, state, now, active)
    results = [await _run_job(engine, source, job) for job in jobs]
    await _end_abandoned_streams(settings, engine, now, recorder)
    if is_full and all(results):
        return replace(state, last_full_import_at=now)
    return state  # a failed full cycle is tried again next time


async def run_forever(
    settings: Settings,
    engine: AsyncEngine,
    source: service.ScheduleSource,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    heartbeat: Path = HEARTBEAT_FILE,
    recorder: Recorder | None = None,
) -> None:
    """Cycle every `event_live_import_interval_seconds` until `stop` is set."""
    state = SchedulerState()
    while not stop.is_set():
        state = await run_cycle(settings, engine, source, state, clock(), recorder)
        heartbeat.touch()
        try:
            await asyncio.wait_for(stop.wait(), settings.event_live_import_interval_seconds)
        except TimeoutError:
            continue  # the interval passed with no stop request: next cycle


async def _run_job(engine: AsyncEngine, source: service.ScheduleSource, job: ImportJob) -> bool:
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            summary = await service.import_schedule(db, source, job.league, job.first_day, job.days)
    except (EventsError, SQLAlchemyError):
        logger.exception("scheduler: %s import from %s failed", job.league, job.first_day)
        return False
    logger.info(
        "scheduler: %s %s..+%dd: %d fetched, %d new, %d updated",
        summary.league,
        summary.first_day,
        summary.days,
        summary.fetched,
        summary.created,
        summary.updated,
        # The same numbers as JSON fields, to filter and chart on.
        extra={"import": summary.model_dump(mode="json")},
    )
    return True


async def _end_abandoned_streams(
    settings: Settings, engine: AsyncEngine, now: datetime, recorder: Recorder | None
) -> None:
    grace = timedelta(seconds=settings.stream_audio_grace_seconds)
    try:
        async with AsyncSession(engine) as db:
            ended = await streams.end_abandoned_streams(
                db, now=now, audio_grace=grace, recorder=recorder
            )
    except SQLAlchemyError:
        logger.exception("scheduler: could not end abandoned streams; trying next cycle")
        return
    logger.info("scheduler: %d abandoned streams ended", len(ended), extra={"ended": len(ended)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="events-scheduler", description="Keep NFL and NBA events current."
    )
    parser.add_argument("--once", action="store_true", help="run one full cycle and exit")
    return parser


async def _main(settings: Settings, once: bool, http_client_factory: HttpClientFactory) -> None:
    engine = create_database_engine(settings)
    recorder = create_recorder(settings)
    try:
        async with http_client_factory(settings.event_source_timeout_seconds) as http:
            source = espn.EspnSchedule(http)
            if once:
                now = datetime.now(UTC)
                await run_cycle(settings, engine, source, SchedulerState(), now, recorder)
                return
            stop = asyncio.Event()
            # SIGTERM (docker stop) and Ctrl+C end the loop between cycles.
            for stop_signal in (signal.SIGTERM, signal.SIGINT):
                asyncio.get_running_loop().add_signal_handler(stop_signal, stop.set)
            logger.info("scheduler: started")
            await run_forever(settings, engine, source, stop, recorder=recorder)
            logger.info("scheduler: stopped")
    finally:
        if recorder is not None:
            await recorder.aclose()
        await engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    http_client_factory: HttpClientFactory = espn.create_http_client,
) -> int:
    args = build_parser().parse_args(argv)
    # pydantic-settings fills the required fields from the environment, which mypy can't see.
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_format)
    asyncio.run(_main(settings, args.once, http_client_factory))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
