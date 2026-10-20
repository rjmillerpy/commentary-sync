import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.models import MAX_TITLE_LENGTH, Event

KICKOFF = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)

pytestmark = pytest.mark.anyio


def new_event(**overrides: object) -> Event:
    fields: dict[str, object] = {
        "source": "espn",
        "source_event_id": "401872999",
        "league": "nfl",
        "title": "Chicago Bears at Atlanta Falcons",
        "home_team": "Atlanta Falcons",
        "away_team": "Chicago Bears",
        "starts_at": KICKOFF,
        "status": "scheduled",
        "networks": ["Fox"],
    }
    fields.update(overrides)
    return Event(**fields)


async def test_event_round_trips_through_the_database(db: AsyncSession) -> None:
    db.add(new_event())
    await db.commit()
    db.expunge_all()

    stored = (await db.execute(select(Event))).scalar_one()
    assert stored.title == "Chicago Bears at Atlanta Falcons"
    assert stored.networks == ["Fox"]
    assert stored.starts_at.replace(tzinfo=UTC) == KICKOFF
    assert isinstance(stored.id, uuid.UUID)
    assert stored.created_at is not None  # filled in by the database
    assert stored.updated_at is not None


async def test_each_event_gets_its_own_id(db: AsyncSession) -> None:
    first, second = new_event(source_event_id="1"), new_event(source_event_id="2")
    db.add_all([first, second])
    await db.commit()
    assert first.id != second.id


async def test_one_row_per_provider_event(db: AsyncSession) -> None:
    """The constraint re-imports rely on: (source, source_event_id) is unique."""
    db.add_all([new_event(), new_event()])
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_the_same_id_from_another_provider_is_a_different_event(db: AsyncSession) -> None:
    db.add_all([new_event(source="espn"), new_event(source="other")])
    await db.commit()


@pytest.mark.parametrize(
    "missing",
    [
        "source",
        "source_event_id",
        "league",
        "title",
        "home_team",
        "away_team",
        "starts_at",
        "status",
        "networks",
    ],
    ids=lambda column: f"without-{column}",
)
async def test_required_columns_are_enforced_by_the_database(
    db: AsyncSession, missing: str
) -> None:
    db.add(new_event(**{missing: None}))
    with pytest.raises(IntegrityError):
        await db.commit()


def test_title_column_is_bounded() -> None:
    title_type = Event.__table__.c.title.type
    assert isinstance(title_type, String)
    assert title_type.length == MAX_TITLE_LENGTH
