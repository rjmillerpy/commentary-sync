import uuid

import pytest
from redis.asyncio import Redis

from app.streams import audience

pytestmark = pytest.mark.anyio

NOW = 1_792_400_000.0
WINDOW = 60


async def test_each_account_counts_once_while_it_keeps_checking_in(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    fan, other = uuid.uuid4(), uuid.uuid4()
    await audience.check_in(cache, stream_id, fan, now=NOW, window_seconds=WINDOW)
    await audience.check_in(
        cache, stream_id, fan, now=NOW + 20, window_seconds=WINDOW
    )  # a second device, or the next check-in
    await audience.check_in(cache, stream_id, other, now=NOW + 20, window_seconds=WINDOW)
    assert await audience.count(cache, [stream_id], now=NOW + 30, window_seconds=WINDOW) == {
        stream_id: 2
    }


@pytest.mark.parametrize(
    ("silent_for", "expected"),
    [(WINDOW - 1, 1), (WINDOW, 1), (WINDOW + 1, 0)],
    ids=["within-the-window", "at-its-edge", "gone"],
)
async def test_a_listener_who_stops_checking_in_stops_counting(
    cache: Redis, silent_for: int, expected: int
) -> None:
    stream_id = uuid.uuid4()
    await audience.check_in(cache, stream_id, uuid.uuid4(), now=NOW, window_seconds=WINDOW)
    counts = await audience.count(cache, [stream_id], now=NOW + silent_for, window_seconds=WINDOW)
    assert counts == {stream_id: expected}


async def test_many_streams_are_counted_together_and_unknown_ones_are_zero(cache: Redis) -> None:
    busy, quiet = uuid.uuid4(), uuid.uuid4()
    await audience.check_in(cache, busy, uuid.uuid4(), now=NOW, window_seconds=WINDOW)
    assert await audience.count(cache, [busy, quiet], now=NOW, window_seconds=WINDOW) == {
        busy: 1,
        quiet: 0,
    }


async def test_no_streams_need_no_round_trip(unreachable_cache: Redis) -> None:
    assert await audience.count(unreachable_cache, [], now=NOW, window_seconds=WINDOW) == {}


async def test_old_check_ins_are_trimmed_and_the_set_expires(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    await audience.check_in(cache, stream_id, uuid.uuid4(), now=NOW, window_seconds=WINDOW)
    await audience.check_in(
        cache, stream_id, uuid.uuid4(), now=NOW + WINDOW + 5, window_seconds=WINDOW
    )
    assert await cache.zcard(audience.key(stream_id)) == 1
    assert await cache.ttl(audience.key(stream_id)) == WINDOW * 2


async def test_with_redis_down_counts_are_unknown_not_an_error(unreachable_cache: Redis) -> None:
    assert (
        await audience.count(unreachable_cache, [uuid.uuid4()], now=NOW, window_seconds=WINDOW)
        is None
    )
