import time

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.common.cache import count_in_window, create_cache
from app.common.config import Settings
from app.main import create_app

FAIL_FAST_SECONDS = 10.0


@pytest.mark.anyio
async def test_unreachable_redis_fails_within_the_timeout(settings: Settings) -> None:
    """Rule 67: a cache that is down must fail the call, not hang it."""
    cache = create_cache(settings)  # the test settings point at a closed port
    started = time.monotonic()
    with pytest.raises(RedisConnectionError):
        await cache.ping()
    assert time.monotonic() - started < FAIL_FAST_SECONDS
    await cache.aclose()


@pytest.mark.anyio
async def test_creating_the_client_does_not_connect(settings: Settings) -> None:
    """Startup must not depend on Redis being up; /health reports it instead."""
    await create_cache(settings).aclose()


@pytest.mark.anyio
async def test_client_returns_text_not_bytes(settings: Settings) -> None:
    cache = create_cache(settings)
    assert cache.connection_pool.connection_kwargs["decode_responses"] is True
    await cache.aclose()


def test_requests_get_the_shared_client(client: TestClient) -> None:
    assert client.get("/health").json()["checks"]["cache"] == "ok"


def test_without_an_override_requests_use_the_configured_client(settings: Settings) -> None:
    """The real client, built at startup from settings that point at a closed port."""
    with TestClient(create_app(settings)) as real_client:
        assert real_client.get("/health").json()["checks"]["cache"] == "unavailable"


@pytest.mark.anyio
async def test_a_window_counter_counts_and_expires_from_its_first_count(cache: Redis) -> None:
    assert await count_in_window(cache, "counter", 60) == (1, 60)
    await cache.expire("counter", 30)  # as if 30 s had passed
    count, remaining = await count_in_window(cache, "counter", 60)
    assert count == 2
    assert remaining == 30  # later counts don't extend the window


@pytest.mark.anyio
async def test_a_window_counter_gives_an_existing_key_an_expiry(cache: Redis) -> None:
    """Regression: a counter with no expiry would never reset."""
    await cache.set("counter", 4)
    assert await count_in_window(cache, "counter", 60) == (5, 60)


@pytest.mark.anyio
async def test_a_window_counter_raises_when_redis_is_down(unreachable_cache: Redis) -> None:
    with pytest.raises(RedisConnectionError):
        await count_in_window(unreachable_cache, "counter", 60)
