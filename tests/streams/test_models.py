import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.commentators.models import Commentator
from app.events.models import Event
from app.streams.models import Stream
from tests.streams.conftest import NOW, add_commentator, add_event

pytestmark = pytest.mark.anyio


async def a_commentator(db: AsyncSession) -> Commentator:
    await add_commentator(db)
    return (await db.execute(select(Commentator))).scalar_one()


async def test_a_stream_round_trips(db: AsyncSession, event: Event) -> None:
    commentator = await a_commentator(db)
    db.add(Stream(commentator_id=commentator.id, event_id=event.id, started_at=NOW))
    await db.commit()
    db.expunge_all()
    stored = (await db.execute(select(Stream))).scalar_one()
    assert (stored.commentator_id, stored.event_id, stored.ended_at) == (
        commentator.id,
        event.id,
        None,
    )


async def test_one_live_stream_per_commentator(db: AsyncSession, event: Event) -> None:
    commentator = await a_commentator(db)
    other_event = await add_event(db, source_id="402")
    db.add_all(
        [
            Stream(commentator_id=commentator.id, event_id=event.id, started_at=NOW),
            Stream(commentator_id=commentator.id, event_id=other_event.id, started_at=NOW),
        ]
    )
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_ended_streams_dont_count_toward_the_one_live_stream(
    db: AsyncSession, event: Event
) -> None:
    commentator = await a_commentator(db)
    db.add_all(
        [
            Stream(commentator_id=commentator.id, event_id=event.id, started_at=NOW, ended_at=NOW),
            Stream(commentator_id=commentator.id, event_id=event.id, started_at=NOW, ended_at=NOW),
            Stream(commentator_id=commentator.id, event_id=event.id, started_at=NOW),
        ]
    )
    await db.commit()
    assert len((await db.execute(select(Stream))).scalars().all()) == 3
