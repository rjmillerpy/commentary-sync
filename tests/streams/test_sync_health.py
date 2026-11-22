import uuid

import pytest
from redis.asyncio import Redis

from app.streams import sync_health
from app.streams.schema import SyncResult, SyncStatus

pytestmark = pytest.mark.anyio

NOW = 1_792_400_000.0
MATCHED = SyncResult(status=SyncStatus.MATCHED, delay_seconds=20.0, peak_ratio=3.0)
NOT_FOUND = SyncResult(status=SyncStatus.NOT_FOUND)


def matched(delay: float) -> SyncResult:
    return SyncResult(status=SyncStatus.MATCHED, delay_seconds=delay, peak_ratio=3.0)


async def test_listeners_count_by_their_latest_result(cache: Redis) -> None:
    stream = uuid.uuid4()
    fan, other, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await sync_health.record(cache, stream, fan, NOT_FOUND, now=NOW)
    await sync_health.record(cache, stream, fan, matched(20), now=NOW + 1)  # tried again: found
    await sync_health.record(cache, stream, other, matched(30), now=NOW + 2)
    await sync_health.record(cache, stream, third, NOT_FOUND, now=NOW + 3)
    health = await sync_health.summary(cache, stream, now=NOW + 10)
    assert health == sync_health.Health(in_sync=2, not_heard=1, typical_delay_seconds=25.0)


async def test_a_listener_who_stopped_syncing_falls_out(cache: Redis) -> None:
    stream = uuid.uuid4()
    await sync_health.record(cache, stream, uuid.uuid4(), MATCHED, now=NOW)
    later = NOW + sync_health.WINDOW_SECONDS + 1
    assert await sync_health.summary(cache, stream, now=later) == sync_health.Health(0, 0, None)


async def test_the_store_goes_once_nobody_syncs(cache: Redis) -> None:
    stream = uuid.uuid4()
    await sync_health.record(cache, stream, uuid.uuid4(), MATCHED, now=NOW)
    assert 0 < await cache.ttl(sync_health.key(stream)) <= sync_health.WINDOW_SECONDS


@pytest.mark.parametrize(
    "stored",
    [
        "not json",
        '{"status": "matched", "delay": null, "at": 1792400000}',
        '{"status": "nope", "delay": 1, "at": 1}',
        '{"status": "not_found", "delay": 3, "at": 1792400000}',
    ],
    ids=["garbage", "match-without-delay", "unknown-status", "miss-with-delay"],
)
async def test_anything_stored_that_isnt_a_result_is_ignored(cache: Redis, stored: str) -> None:
    stream = uuid.uuid4()
    await cache.hset(sync_health.key(stream), "someone", stored)
    assert await sync_health.summary(cache, stream, now=NOW) == sync_health.Health(0, 0, None)


async def test_with_redis_down_a_result_is_lost_not_the_sync(unreachable_cache: Redis) -> None:
    await sync_health.record(
        unreachable_cache, uuid.uuid4(), uuid.uuid4(), MATCHED, now=NOW
    )  # no raise
    assert await sync_health.summary(unreachable_cache, uuid.uuid4(), now=NOW) is None
