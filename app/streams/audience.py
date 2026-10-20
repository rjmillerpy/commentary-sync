"""Who is listening to each live stream, right now: live listener state in Redis.

A listener's app checks in (POST /streams/{id}/listening) every 20 s while it
plays a stream. Each stream has a sorted set of account IDs scored by their
last check-in; anyone who hasn't checked in for `listener_window_seconds` no
longer counts. One account counts once, however many devices it plays on.

Counts are a nicety, not a function: if Redis is down, callers get None and
carry on (a list of streams still loads).
"""

import logging
import uuid
from collections.abc import Sequence

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

KEY_PREFIX = "listeners:"


def key(stream_id: uuid.UUID) -> str:
    return f"{KEY_PREFIX}{stream_id}"


async def check_in(
    cache: Redis, stream_id: uuid.UUID, account_id: uuid.UUID, *, now: float, window_seconds: int
) -> None:
    """Count this account as listening for the next `window_seconds`. Raises RedisError."""
    stream_key = key(stream_id)
    async with cache.pipeline(transaction=True) as pipe:
        pipe.zadd(stream_key, {str(account_id): now})
        pipe.zremrangebyscore(stream_key, "-inf", now - window_seconds)
        # The set outlives its last listener by one window, then goes.
        pipe.expire(stream_key, window_seconds * 2)
        await pipe.execute()


async def count(
    cache: Redis, stream_ids: Sequence[uuid.UUID], *, now: float, window_seconds: int
) -> dict[uuid.UUID, int] | None:
    """Listeners per stream, in one round trip; None if Redis can't say."""
    if not stream_ids:
        return {}
    since = now - window_seconds
    try:
        async with cache.pipeline(transaction=False) as pipe:
            for stream_id in stream_ids:
                pipe.zcount(key(stream_id), since, "+inf")
            counts = await pipe.execute()
    except RedisError:
        logger.warning("listener counts unavailable", exc_info=True)
        return None
    return {stream_id: int(found) for stream_id, found in zip(stream_ids, counts, strict=True)}
