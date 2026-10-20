"""Login lockout: count wrong passwords per account in Redis.

The count starts at the first failure and expires `window_seconds` later, so a
lockout always ends by itself. It is keyed by a hash of the email, so Redis
holds no addresses.
"""

import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.auth.errors import AuthUnavailableError
from app.common.cache import count_in_window

KEY_PREFIX = "auth:login-failures:"
NO_EXPIRY = -1  # what TTL returns for a key that never expires


def failure_key(email: str) -> str:
    return KEY_PREFIX + hashlib.sha256(email.encode()).hexdigest()


async def seconds_locked(
    cache: Redis, email: str, *, max_failures: int, window_seconds: int
) -> int:
    """How long logins to this account stay refused; 0 when they are allowed."""
    key = failure_key(email)
    try:
        failures = await cache.get(key)
        if failures is None or int(failures) < max_failures:
            return 0
        remaining = await cache.ttl(key)
        if remaining == NO_EXPIRY:
            # Written by something other than record_failure. Without an expiry
            # the account would stay locked forever, so give it one.
            await cache.expire(key, window_seconds)
            return window_seconds
    except RedisError as error:
        raise AuthUnavailableError("login lockout store unavailable") from error
    # The key can expire between the two reads (TTL -2); never report under 1 s.
    return max(remaining, 1)


async def record_failure(cache: Redis, email: str, *, window_seconds: int) -> None:
    """Count one wrong password. The count's expiry is set with it: one left
    without an expiry would lock the account forever."""
    try:
        await count_in_window(cache, failure_key(email), window_seconds)
    except RedisError as error:
        raise AuthUnavailableError("login lockout store unavailable") from error


async def clear_failures(cache: Redis, email: str) -> None:
    try:
        await cache.delete(failure_key(email))
    except RedisError as error:
        raise AuthUnavailableError("login lockout store unavailable") from error
