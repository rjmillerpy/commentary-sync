"""Command-line import of NFL and NBA schedules.

uv run events-import --league nfl --days 7
docker compose exec api python -m app.events.cli --league nba
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

import httpx2
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cli_arguments import bounded_number
from app.common.config import MAX_IMPORT_DAYS, Settings
from app.common.db import create_database_engine
from app.common.logs import configure_logging
from app.events import espn, service
from app.events.errors import EventsError
from app.events.schema import ImportSummary, League

EXIT_OK = 0
EXIT_ERROR = 2
DEFAULT_DAYS = 7

HttpClientFactory = Callable[[float], httpx2.AsyncClient]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="events-import", description="Import a league's schedule from ESPN."
    )
    parser.add_argument("--league", type=League, choices=list(League), required=True)
    parser.add_argument(
        "--start", type=date.fromisoformat, help="first day, YYYY-MM-DD (default: today, UTC)"
    )
    parser.add_argument(
        "--days",
        type=bounded_number(int, 1, MAX_IMPORT_DAYS),
        default=DEFAULT_DAYS,
    )
    return parser


def format_summary(summary: ImportSummary) -> str:
    return (
        f"{summary.league}: {summary.fetched} events over {summary.days} days "
        f"from {summary.first_day}: {summary.created} new, {summary.updated} updated"
    )


async def run_import(
    settings: Settings, args: argparse.Namespace, http_client_factory: HttpClientFactory
) -> ImportSummary:
    first_day: date = args.start or datetime.now(UTC).date()
    engine = create_database_engine(settings)
    try:
        async with (
            http_client_factory(settings.event_source_timeout_seconds) as http,
            AsyncSession(engine, expire_on_commit=False) as db,
        ):
            source = espn.EspnSchedule(http)
            return await service.import_schedule(db, source, args.league, first_day, args.days)
    finally:
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
    try:
        summary = asyncio.run(run_import(settings, args, http_client_factory))
    except EventsError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(format_summary(summary))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
