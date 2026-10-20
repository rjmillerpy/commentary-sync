import uuid

import numpy as np
import pytest
from redis.asyncio import Redis

from app.streams import reference

pytestmark = pytest.mark.anyio

NOW = 1_792_342_800.0
WINDOW = 240
RATE = reference.SAMPLE_RATE


def pcm(seconds: float, value: int = 1000) -> bytes:
    return np.full(int(seconds * RATE), value, dtype="<i2").tobytes()


async def test_chunks_come_back_as_one_timeline(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    for second in (0, 1, 2):
        await reference.add_chunk(
            cache,
            stream_id,
            NOW + second,
            pcm(1, 1000 * (second + 1)),
            window_seconds=WINDOW,
            now=NOW,
        )
    stored = await reference.load(cache, stream_id)
    assert stored is not None
    assert stored.start == NOW
    assert len(stored.samples) == 3 * RATE
    assert stored.samples[[0, RATE, 2 * RATE]] == pytest.approx(
        [1000 / 32768, 2000 / 32768, 3000 / 32768]
    )


async def test_a_missing_chunk_stays_silent_so_later_audio_keeps_its_time(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    await reference.add_chunk(cache, stream_id, NOW, pcm(1), window_seconds=WINDOW, now=NOW)
    await reference.add_chunk(cache, stream_id, NOW + 3, pcm(1), window_seconds=WINDOW, now=NOW)
    stored = await reference.load(cache, stream_id)
    assert stored is not None
    assert len(stored.samples) == 4 * RATE
    assert not stored.samples[RATE : 3 * RATE].any()
    assert stored.samples[3 * RATE] > 0


async def test_audio_older_than_the_window_is_dropped(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    await reference.add_chunk(
        cache, stream_id, NOW - WINDOW - 5, pcm(1), window_seconds=WINDOW, now=NOW - WINDOW
    )
    await reference.add_chunk(cache, stream_id, NOW, pcm(1), window_seconds=WINDOW, now=NOW)
    stored = await reference.load(cache, stream_id)
    assert stored is not None
    assert stored.start == NOW


async def test_the_reference_expires_after_the_stream_goes_quiet(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    await reference.add_chunk(cache, stream_id, NOW, pcm(1), window_seconds=WINDOW, now=NOW)
    assert await cache.ttl(reference.key(stream_id)) == WINDOW + reference.EXPIRY_GRACE_SECONDS


async def test_nothing_stored_is_none(cache: Redis) -> None:
    assert await reference.load(cache, uuid.uuid4()) is None


async def test_members_that_arent_chunks_are_skipped(cache: Redis) -> None:
    stream_id = uuid.uuid4()
    await cache.zadd(reference.key(stream_id), {"not a chunk": NOW, "1.0:!!!": NOW})
    assert await reference.load(cache, stream_id) is None


@pytest.mark.parametrize(
    ("data", "valid"),
    [(pcm(1), True), (pcm(10), True), (b"", False), (b"\x00", False), (pcm(10.1), False)],
    ids=["one-second", "ten-seconds", "empty", "half-a-sample", "over-ten-seconds"],
)
def test_chunks_are_whole_samples_up_to_ten_seconds(data: bytes, valid: bool) -> None:
    assert reference.is_valid_pcm(data) is valid
