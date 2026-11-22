"""How well each live stream's listeners are syncing: for the commentator's studio.

Every sync a listener's phone asks for (POST /streams/{id}/sync, by hand or
the app's automatic re-checks every 5 minutes) leaves its result here: per
stream, a Redis hash from listener ID to their latest result and when. A
summary counts the listeners whose latest result is recent: in sync, or not
heard (their TV's sound wasn't found in the commentator's: a different
broadcast, a quiet TV), and the typical delay they play the commentary at,
which is how late listeners hear the commentator.

Like the listener counts, this is a nicety: Redis being down loses a result
or a summary, never a sync.
"""

import logging
import statistics
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.streams.schema import SyncResult, SyncStatus

logger = logging.getLogger(__name__)

KEY_PREFIX = "sync-health:"
# Two automatic re-checks: a listener who stopped syncing falls out after this.
WINDOW_SECONDS = 10 * 60


@dataclass(frozen=True)
class Health:
    in_sync: int
    not_heard: int
    typical_delay_seconds: float | None


class _Entry(BaseModel):
    """One listener's latest result, as stored; read back like any input (rule 5)."""

    status: SyncStatus
    delay: float | None
    at: float


def key(stream_id: uuid.UUID) -> str:
    return f"{KEY_PREFIX}{stream_id}"


async def record(
    cache: Redis, stream_id: uuid.UUID, listener_id: uuid.UUID, result: SyncResult, *, now: float
) -> None:
    """Keep this listener's latest result. Best effort: a Redis failure is logged."""
    entry = _Entry(status=result.status, delay=result.delay_seconds, at=now).model_dump_json()
    try:
        async with cache.pipeline(transaction=True) as pipe:
            pipe.hset(key(stream_id), str(listener_id), entry)
            pipe.expire(key(stream_id), WINDOW_SECONDS)
            await pipe.execute()
    except RedisError:
        logger.warning("sync result for stream %s not kept", stream_id, exc_info=True)


async def summary(cache: Redis, stream_id: uuid.UUID, *, now: float) -> Health | None:
    """The stream's listeners by their latest recent result; None if Redis can't say."""
    try:
        stored = await cache.hgetall(key(stream_id))
    except RedisError:
        logger.warning("sync health for stream %s unavailable", stream_id, exc_info=True)
        return None
    entries = [_parse(raw) for raw in stored.values()]
    recent = [entry for entry in entries if entry is not None and entry.at >= now - WINDOW_SECONDS]
    delays = [entry.delay for entry in recent if entry.delay is not None]
    return Health(
        in_sync=len(delays),
        not_heard=len(recent) - len(delays),
        typical_delay_seconds=statistics.median(delays) if delays else None,
    )


def _parse(raw: bytes | str) -> _Entry | None:
    """One stored result, or None if it isn't one; only a match has a delay."""
    try:
        entry = _Entry.model_validate_json(raw)
    except ValidationError:
        return None
    is_whole = (entry.status == SyncStatus.MATCHED) == (entry.delay is not None)
    return entry if is_whole else None
