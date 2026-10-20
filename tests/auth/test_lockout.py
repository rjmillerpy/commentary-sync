from collections.abc import Awaitable, Callable

import pytest
from redis.asyncio import Redis

from app.auth import lockout
from app.auth.errors import AuthUnavailableError

pytestmark = pytest.mark.anyio

EMAIL = "fan@example.com"
MAX_FAILURES = 3
WINDOW = 600


async def locked_for(cache: Redis) -> int:
    return await lockout.seconds_locked(
        cache, EMAIL, max_failures=MAX_FAILURES, window_seconds=WINDOW
    )


async def fail(cache: Redis, times: int) -> None:
    for _ in range(times):
        await lockout.record_failure(cache, EMAIL, window_seconds=WINDOW)


@pytest.mark.parametrize(
    ("failures", "is_locked"),
    [(0, False), (MAX_FAILURES - 1, False), (MAX_FAILURES, True), (MAX_FAILURES + 2, True)],
    ids=["none", "one-short", "at-limit", "past-limit"],
)
async def test_locks_at_the_limit(cache: Redis, failures: int, is_locked: bool) -> None:
    await fail(cache, failures)
    seconds = await locked_for(cache)
    assert (0 < seconds <= WINDOW) if is_locked else seconds == 0


async def test_the_window_starts_at_the_first_failure(cache: Redis) -> None:
    """Later failures don't push the end of the window back."""
    await fail(cache, 1)
    await cache.expire(lockout.failure_key(EMAIL), 100)
    await fail(cache, MAX_FAILURES)
    assert await locked_for(cache) <= 100


async def test_clearing_unlocks(cache: Redis) -> None:
    await fail(cache, MAX_FAILURES)
    await lockout.clear_failures(cache, EMAIL)
    assert await locked_for(cache) == 0


async def test_a_count_with_no_expiry_is_given_one(cache: Redis) -> None:
    await cache.set(lockout.failure_key(EMAIL), MAX_FAILURES)
    assert await locked_for(cache) == WINDOW
    assert 0 < await cache.ttl(lockout.failure_key(EMAIL)) <= WINDOW


async def test_redis_holds_no_email_addresses(cache: Redis) -> None:
    await fail(cache, 1)
    keys = await cache.keys("*")
    assert keys == [lockout.failure_key(EMAIL)]
    assert EMAIL not in keys[0]


async def test_emails_get_separate_counts(cache: Redis) -> None:
    await fail(cache, MAX_FAILURES)
    other = await lockout.seconds_locked(
        cache, "other@example.com", max_failures=MAX_FAILURES, window_seconds=WINDOW
    )
    assert other == 0


@pytest.mark.parametrize(
    "operation",
    [
        locked_for,
        lambda cache: lockout.record_failure(cache, EMAIL, window_seconds=WINDOW),
        lambda cache: lockout.clear_failures(cache, EMAIL),
    ],
    ids=["check", "record", "clear"],
)
async def test_a_redis_outage_is_a_domain_error(
    unreachable_cache: Redis, operation: Callable[[Redis], Awaitable[object]]
) -> None:
    with pytest.raises(AuthUnavailableError):
        await operation(unreachable_cache)
