"""Import schedules into the events table, and read events back."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import MAX_IMPORT_DAYS
from app.events.errors import EventNotFoundError, InvalidImportWindowError
from app.events.models import Event
from app.events.schema import EventStatus, ImportSummary, League, ScheduledEvent

# Listings start this far in the past by default, so games in progress show.
LIVE_LOOKBACK = timedelta(hours=4)
# A league counts as active from shortly before its first game until its last
# game should be over. A game ESPN still calls live is followed for longer
# (overtime, delays), but not forever.
ACTIVE_LEAD = timedelta(minutes=30)
MAX_LIVE_AGE = timedelta(hours=12)


class ScheduleSource(Protocol):
    """A schedule provider, for example app.events.espn.EspnSchedule."""

    name: str

    async def fetch_day(self, league: League, day: date) -> list[ScheduledEvent]: ...


async def import_schedule(
    db: AsyncSession, source: ScheduleSource, league: League, first_day: date, days: int
) -> ImportSummary:
    """Fetch `days` days of a league's schedule and create or update their events."""
    if not 1 <= days <= MAX_IMPORT_DAYS:
        raise InvalidImportWindowError(f"days must be between 1 and {MAX_IMPORT_DAYS}")

    # One request per day, one after another: at most 31, and gentle on the provider.
    fetched: dict[str, ScheduledEvent] = {}
    for offset in range(days):
        for event in await source.fetch_day(league, first_day + timedelta(days=offset)):
            fetched[event.source_event_id] = event

    created, updated = await _upsert(db, source.name, list(fetched.values()))
    await db.commit()
    return ImportSummary(
        league=league,
        first_day=first_day,
        days=days,
        fetched=len(fetched),
        created=created,
        updated=updated,
    )


async def list_events(
    db: AsyncSession,
    *,
    league: League | None,
    starts_after: datetime | None,
    limit: int,
    offset: int,
) -> Sequence[Event]:
    """Events in start-time order, from `starts_after` (default: a few hours ago)."""
    since = starts_after if starts_after is not None else datetime.now(UTC) - LIVE_LOOKBACK
    query = select(Event).where(Event.starts_at >= since)
    if league is not None:
        query = query.where(Event.league == league)
    query = query.order_by(Event.starts_at, Event.id).limit(limit).offset(offset)
    return (await db.execute(query)).scalars().all()


async def active_leagues(db: AsyncSession, now: datetime) -> set[League]:
    """Leagues with a game starting soon, in progress, or recently started."""
    is_around_kickoff = Event.starts_at.between(now - LIVE_LOOKBACK, now + ACTIVE_LEAD)
    is_still_live = (Event.status == EventStatus.LIVE) & (Event.starts_at >= now - MAX_LIVE_AGE)
    query = select(Event.league).where(is_around_kickoff | is_still_live).distinct()
    return {League(league) for league in (await db.execute(query)).scalars()}


async def get_event(db: AsyncSession, event_id: uuid.UUID) -> Event:
    event = await db.get(Event, event_id)
    if event is None:
        raise EventNotFoundError(f"no event with id {event_id}")
    return event


async def _upsert(
    db: AsyncSession, source_name: str, events: list[ScheduledEvent]
) -> tuple[int, int]:
    """Create new events and update known ones, with one query for the lookup."""
    if not events:
        return 0, 0
    existing_query = select(Event).where(
        Event.source == source_name,
        Event.source_event_id.in_([event.source_event_id for event in events]),
    )
    existing = {row.source_event_id: row for row in (await db.execute(existing_query)).scalars()}
    new_events = [event for event in events if event.source_event_id not in existing]
    for event in events:
        if event.source_event_id in existing:
            _apply(existing[event.source_event_id], event)
    db.add_all([_apply(Event(), event) for event in new_events])
    return len(new_events), len(events) - len(new_events)


def _apply(row: Event, event: ScheduledEvent) -> Event:
    row.source = event.source
    row.source_event_id = event.source_event_id
    row.league = event.league
    row.title = event.title
    row.home_team = event.home_team
    row.away_team = event.away_team
    row.starts_at = event.starts_at
    row.status = event.status
    row.networks = list(event.networks)
    return row
