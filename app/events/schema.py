"""Value objects and request/response shapes for the events domain."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from app.common.pagination import Page
from app.common.schema import FrozenModel


class League(StrEnum):
    NFL = "nfl"
    NBA = "nba"


class EventStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINAL = "final"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class ScheduledEvent(FrozenModel):
    """One event as a schedule provider describes it, before it is stored."""

    source: str
    source_event_id: str
    league: League
    title: str
    home_team: str
    away_team: str
    starts_at: datetime
    status: EventStatus
    networks: tuple[str, ...]  # national TV networks, for example ("CBS",)


class ImportSummary(FrozenModel):
    league: League
    first_day: date
    days: int
    fetched: int
    created: int
    updated: int


class EventResponse(FrozenModel):
    id: uuid.UUID
    league: League
    title: str
    home_team: str
    away_team: str
    starts_at: datetime
    status: EventStatus
    networks: list[str]


class EventPage(Page[EventResponse]):
    """One page of events in start-time order."""
