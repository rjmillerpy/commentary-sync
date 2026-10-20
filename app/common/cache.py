"""The Redis boundary: one shared client for live listener state."""

from fastapi import Request
from redis.asyncio import Redis

from app.common.config import Settings


def create_cache(settings: Settings) -> Redis:
    """Build the app's one Redis client. Nothing connects until first use.

    Every command gets a timeout. Commands are not retried here: callers decide
    what a cache outage means for them.
    """
    return Redis.from_url(
        settings.cache_url.get_secret_value(),
        socket_connect_timeout=settings.cache_timeout_seconds,
        socket_timeout=settings.cache_timeout_seconds,
        decode_responses=True,
    )


def get_cache(request: Request) -> Redis:
    """FastAPI dependency: the shared Redis client."""
    cache: Redis = request.app.state.cache
    return cache


async def count_in_window(cache: Redis, key: str, window_seconds: int) -> tuple[int, int]:
    """Add one to a counter that expires `window_seconds` after its first count.

    Returns the count and the seconds until it expires. The increment and the
    expiry are one transaction: a counter left without an expiry would never
    reset. Raises RedisError; the caller decides what an outage means.
    """
    async with cache.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        pipe.ttl(key)
        count, _, remaining = await pipe.execute()
    return int(count), int(remaining)
