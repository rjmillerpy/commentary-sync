import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.events.schema import EventPage, EventResponse, EventStatus, League, ScheduledEvent

KICKOFF = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("member", "wire_value"),
    [(League.NFL, "nfl"), (League.NBA, "nba")],
    ids=["nfl", "nba"],
)
def test_league_wire_values_are_stable(member: League, wire_value: str) -> None:
    assert member.value == wire_value


@pytest.mark.parametrize(
    "status", ["scheduled", "live", "final", "postponed", "cancelled"], ids=str
)
def test_status_wire_values_are_stable(status: str) -> None:
    assert EventStatus(status).value == status


def test_scheduled_events_are_immutable() -> None:
    event = ScheduledEvent(
        source="espn",
        source_event_id="1",
        league=League.NFL,
        title="Jets at Patriots",
        home_team="New England Patriots",
        away_team="New York Jets",
        starts_at=KICKOFF,
        status=EventStatus.SCHEDULED,
        networks=("CBS",),
    )
    with pytest.raises(ValidationError):
        event.title = "changed"


def test_event_response_rejects_an_unknown_league() -> None:
    with pytest.raises(ValidationError):
        EventResponse.model_validate(
            {
                "id": str(uuid.uuid4()),
                "league": "mlb",
                "title": "t",
                "home_team": "h",
                "away_team": "a",
                "starts_at": KICKOFF.isoformat(),
                "status": "scheduled",
                "networks": [],
            }
        )


@pytest.mark.parametrize(
    ("limit", "offset"),
    [(0, 0), (101, 0), (10, -1)],
    ids=["limit-zero", "limit-over", "offset-negative"],
)
def test_event_page_bounds(limit: int, offset: int) -> None:
    with pytest.raises(ValidationError):
        EventPage(items=[], limit=limit, offset=offset, next_offset=None)
