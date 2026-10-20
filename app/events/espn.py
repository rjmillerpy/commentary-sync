"""ESPN's public scoreboard API: the schedule provider for NFL and NBA events.

The API is free and needs no key, but it is undocumented and unofficial: ESPN
publishes no terms for it and can change or block it at any time. Everything
ESPN-specific stays in this module, so another provider can replace it by
offering the same `fetch_day`.
"""

import asyncio
import logging
from datetime import date, datetime
from http import HTTPStatus

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.events.errors import EventSourceError
from app.events.schema import EventStatus, League, ScheduledEvent

logger = logging.getLogger(__name__)

SOURCE_NAME = "espn"
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
LEAGUE_PATHS = {League.NFL: "football/nfl", League.NBA: "basketball/nba"}
DATE_FORMAT = "%Y%m%d"
USER_AGENT = "commentary-sync/0.1 (schedule import)"

MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 1.0  # doubled after each failed attempt
HOME = "home"
AWAY = "away"

# A few statuses have their own name; everything else is told apart by state.
STATUS_BY_NAME = {
    "STATUS_POSTPONED": EventStatus.POSTPONED,
    "STATUS_CANCELED": EventStatus.CANCELLED,
}
STATUS_BY_STATE = {"pre": EventStatus.SCHEDULED, "in": EventStatus.LIVE, "post": EventStatus.FINAL}


class _Payload(BaseModel):
    """The slice of ESPN's response we read; everything else is ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class _StatusType(_Payload):
    name: str
    state: str


class _Status(_Payload):
    type: _StatusType


class _Team(_Payload):
    displayName: str  # noqa: N815 - ESPN's field name


class _Competitor(_Payload):
    homeAway: str  # noqa: N815 - ESPN's field name
    team: _Team


class _Broadcast(_Payload):
    names: list[str] = []


class _Competition(_Payload):
    status: _Status
    competitors: list[_Competitor] = Field(min_length=2)
    broadcasts: list[_Broadcast] = []


class _Event(_Payload):
    id: str
    date: datetime
    name: str
    competitions: list[_Competition] = Field(min_length=1)


class _Scoreboard(_Payload):
    events: list[_Event]


def create_http_client(timeout_seconds: float) -> httpx2.AsyncClient:
    """One client per import run, with a timeout on every request."""
    return httpx2.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx2.Timeout(timeout_seconds),
        headers={"User-Agent": USER_AGENT},
    )


class EspnSchedule:
    """Reads one day of a league's schedule from ESPN."""

    name = SOURCE_NAME

    def __init__(
        self,
        http: httpx2.AsyncClient,
        *,
        retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        self._http = http
        self._retry_delay_seconds = retry_delay_seconds

    async def fetch_day(self, league: League, day: date) -> list[ScheduledEvent]:
        path = f"/{LEAGUE_PATHS[league]}/scoreboard"
        body = await self._get(path, {"dates": day.strftime(DATE_FORMAT)})
        try:
            scoreboard = _Scoreboard.model_validate_json(body)
        except ValidationError as error:
            raise EventSourceError(f"ESPN sent an unexpected {league} schedule") from error
        return [_to_scheduled_event(league, event) for event in scoreboard.events]

    async def _get(self, path: str, params: dict[str, str]) -> bytes:
        """GET with bounded retries. Network errors, 429 and 5xx are retried;
        any other error status is final, because repeating it can't help."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._http.get(path, params=params)
            except httpx2.TransportError as error:
                failure = f"{type(error).__name__}"
            else:
                if response.is_success:
                    return response.content
                if not _is_retryable(response.status_code):
                    raise EventSourceError(f"ESPN answered {response.status_code} for {path}")
                failure = f"HTTP {response.status_code}"
            logger.warning("ESPN %s attempt %d/%d failed: %s", path, attempt, MAX_ATTEMPTS, failure)
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(self._retry_delay_seconds * 2 ** (attempt - 1))
        raise EventSourceError(f"ESPN did not answer for {path} after {MAX_ATTEMPTS} attempts")


def _is_retryable(status_code: int) -> bool:
    is_rate_limited = status_code == HTTPStatus.TOO_MANY_REQUESTS
    return is_rate_limited or status_code >= HTTPStatus.INTERNAL_SERVER_ERROR


def _to_scheduled_event(league: League, event: _Event) -> ScheduledEvent:
    competition = event.competitions[0]
    teams = {
        competitor.homeAway: competitor.team.displayName for competitor in competition.competitors
    }
    if HOME not in teams or AWAY not in teams:
        raise EventSourceError(f"ESPN event {event.id} has no home and away team")
    networks = (name for broadcast in competition.broadcasts for name in broadcast.names)
    return ScheduledEvent(
        source=SOURCE_NAME,
        source_event_id=event.id,
        league=league,
        title=event.name,
        home_team=teams[HOME],
        away_team=teams[AWAY],
        starts_at=event.date,
        status=_status(competition.status.type),
        networks=tuple(dict.fromkeys(networks)),  # de-duplicated, order kept
    )


def _status(status_type: _StatusType) -> EventStatus:
    if status_type.name in STATUS_BY_NAME:
        return STATUS_BY_NAME[status_type.name]
    if status_type.state in STATUS_BY_STATE:
        return STATUS_BY_STATE[status_type.state]
    raise EventSourceError(f"ESPN status {status_type.name!r} ({status_type.state!r}) is unknown")
