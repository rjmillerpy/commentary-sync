import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import Settings
from app.events.models import Event
from app.simulation.broadcast import SOURCE_SAMPLE_RATE
from app.simulation.service import to_analysis_rate
from app.streams import reference, service, tv_sync
from app.streams.errors import (
    CaptureTimeError,
    StreamEndedError,
    StreamNotFoundError,
    SyncAudioError,
)
from app.streams.models import Stream
from app.streams.schema import GoLive, SyncStatus
from app.sync.schema import Samples
from app.sync.service import extract_features
from tests.streams.conftest import add_commentator, add_user

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 19, 17, 30, tzinfo=UTC)
# The commentator's room audio starts a minute ago, in server time.
REFERENCE_START = NOW.timestamp() - 60
CHUNK_SECONDS = 5
# Where the listener's recording starts in the broadcast, and how long it is.
QUERY_AT = 12.0
QUERY_SECONDS = 10.0
TOLERANCE = 0.1  # seconds: frames are 10 ms; the encoder adds a little


async def live_stream(db: AsyncSession, event: Event) -> Stream:
    user = await add_commentator(db)
    return await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)


async def store_reference(
    cache: Redis, stream_id: uuid.UUID, samples: Samples, settings: Settings
) -> None:
    """The studio's uploads: `samples` (8 kHz) in 5 s chunks from REFERENCE_START."""
    pcm = np.clip(samples * 32767, -32768, 32767).astype("<i2")
    step = CHUNK_SECONDS * reference.SAMPLE_RATE
    for index, start in enumerate(range(0, len(pcm), step)):
        await reference.add_chunk(
            cache,
            stream_id,
            REFERENCE_START + index * CHUNK_SECONDS,
            pcm[start : start + step].tobytes(),
            window_seconds=settings.sync_reference_seconds,
            now=NOW.timestamp(),
        )


def tv_features(source: Samples, start: float = QUERY_AT, seconds: float = QUERY_SECONDS) -> bytes:
    """What the listener's phone sends: the matcher's features of what it
    heard (client/src/features.ts computes the same), never the audio."""
    first = int(start * SOURCE_SAMPLE_RATE)
    heard = to_analysis_rate(source[first : first + int(seconds * SOURCE_SAMPLE_RATE)])
    return extract_features(heard).astype("<f4").tobytes()


@pytest.mark.parametrize(
    "behind",
    [7.5, 0.0, -4.0],
    ids=["listener-tv-behind", "level", "listener-tv-ahead"],
)
async def test_the_delay_is_how_far_the_listeners_tv_is_behind_the_commentators(
    db: AsyncSession,
    cache: Redis,
    event: Event,
    settings: Settings,
    broadcast: Samples,
    analysis_broadcast: Samples,
    behind: float,
) -> None:
    stream = await live_stream(db, event)
    await store_reference(cache, stream.id, analysis_broadcast, settings)
    # The commentator's TV played second 12 at REFERENCE_START + 12;
    # the listener's plays it `behind` seconds later.
    captured_at = REFERENCE_START + QUERY_AT + behind
    result = await tv_sync.measure_delay(
        db, cache, stream.id, tv_features(broadcast), captured_at, now=NOW
    )
    assert result.status is SyncStatus.MATCHED
    assert result.delay_seconds == pytest.approx(behind, abs=TOLERANCE)
    assert result.peak_ratio is not None and result.peak_ratio > 1.0


async def test_a_different_broadcast_is_not_found(
    db: AsyncSession,
    cache: Redis,
    event: Event,
    settings: Settings,
    other_broadcast: Samples,
    analysis_broadcast: Samples,
) -> None:
    stream = await live_stream(db, event)
    await store_reference(cache, stream.id, analysis_broadcast, settings)
    recording = tv_features(other_broadcast)
    result = await tv_sync.measure_delay(
        db, cache, stream.id, recording, REFERENCE_START + 20, now=NOW
    )
    assert (result.status, result.delay_seconds) == (SyncStatus.NOT_FOUND, None)


async def test_without_a_reference_nothing_is_found(
    db: AsyncSession, cache: Redis, event: Event, broadcast: Samples
) -> None:
    stream = await live_stream(db, event)
    result = await tv_sync.measure_delay(
        db, cache, stream.id, tv_features(broadcast), REFERENCE_START, now=NOW
    )
    assert result.status is SyncStatus.NOT_FOUND


@pytest.mark.parametrize(
    "seconds_ago",
    [tv_sync.MAX_CAPTURE_AGE_SECONDS + 1, -tv_sync.MAX_CAPTURE_LEAD_SECONDS - 1],
    ids=["too-old", "from-the-future"],
)
async def test_a_capture_time_far_from_the_servers_clock_is_refused(
    db: AsyncSession,
    cache: Redis,
    event: Event,
    broadcast: Samples,
    seconds_ago: float,
) -> None:
    stream = await live_stream(db, event)
    with pytest.raises(CaptureTimeError):
        await tv_sync.measure_delay(
            db,
            cache,
            stream.id,
            tv_features(broadcast),
            NOW.timestamp() - seconds_ago,
            now=NOW,
        )


@pytest.mark.parametrize(
    "case",
    ["ragged", "too-short", "too-long", "not-numbers"],
    ids=["ragged", "too-short", "too-long", "not-numbers"],
)
async def test_features_that_cant_be_used_are_refused(
    db: AsyncSession,
    cache: Redis,
    event: Event,
    broadcast: Samples,
    case: str,
) -> None:
    recordings: dict[str, Callable[[], bytes]] = {
        "ragged": lambda: b"\x00" * 5,
        "too-short": lambda: tv_features(broadcast, seconds=2),
        "too-long": lambda: tv_features(broadcast, start=0, seconds=25),
        "not-numbers": lambda: np.full((400, 16), np.nan, dtype="<f4").tobytes(),
    }
    stream = await live_stream(db, event)
    with pytest.raises(SyncAudioError):
        await tv_sync.measure_delay(
            db, cache, stream.id, recordings[case](), REFERENCE_START + 30, now=NOW
        )


async def test_an_ended_stream_cant_be_synced(
    db: AsyncSession, cache: Redis, event: Event, broadcast: Samples
) -> None:
    stream = await live_stream(db, event)
    await service.end_stream(db, stream.commentator.user, stream.id, now=NOW)
    with pytest.raises(StreamEndedError):
        await tv_sync.measure_delay(
            db, cache, stream.id, tv_features(broadcast), REFERENCE_START, now=NOW
        )


async def test_the_commentator_adds_to_their_own_streams_reference(
    db: AsyncSession, cache: Redis, event: Event, settings: Settings
) -> None:
    stream = await live_stream(db, event)
    pcm = np.zeros(reference.SAMPLE_RATE, dtype="<i2").tobytes()
    await tv_sync.add_reference(
        db, cache, stream.commentator.user, stream.id, NOW.timestamp(), pcm, settings, now=NOW
    )
    stored = await reference.load(cache, stream.id)
    assert stored is not None
    assert stored.start == NOW.timestamp()


async def test_nobody_else_can_add_to_a_streams_reference(
    db: AsyncSession, cache: Redis, event: Event, settings: Settings
) -> None:
    """Security: only the stream's own commentator decides what listeners are matched against."""
    stream = await live_stream(db, event)
    stranger = await add_user(db, "stranger@example.com", "Stranger")
    with pytest.raises(StreamNotFoundError):
        await tv_sync.add_reference(
            db, cache, stranger, stream.id, NOW.timestamp(), b"\x00\x00", settings, now=NOW
        )


@pytest.mark.parametrize(
    ("pcm", "captured_at", "error"),
    [
        (b"\x00", NOW.timestamp(), SyncAudioError),
        (b"\x00\x00", NOW.timestamp() - 600, CaptureTimeError),
    ],
    ids=["half-a-sample", "stale"],
)
async def test_bad_reference_chunks_are_refused(
    db: AsyncSession,
    cache: Redis,
    event: Event,
    settings: Settings,
    pcm: bytes,
    captured_at: float,
    error: type[Exception],
) -> None:
    stream = await live_stream(db, event)
    with pytest.raises(error):
        await tv_sync.add_reference(
            db, cache, stream.commentator.user, stream.id, captured_at, pcm, settings, now=NOW
        )


async def test_syncs_are_logged_by_stream_with_the_delay_never_the_audio(
    db: AsyncSession,
    cache: Redis,
    event: Event,
    settings: Settings,
    broadcast: Samples,
    analysis_broadcast: Samples,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stream = await live_stream(db, event)
    await store_reference(cache, stream.id, analysis_broadcast, settings)
    with caplog.at_level(logging.INFO, logger=tv_sync.__name__):
        await tv_sync.measure_delay(
            db,
            cache,
            stream.id,
            tv_features(broadcast),
            REFERENCE_START + QUERY_AT + 3,
            now=NOW,
        )
    record = caplog.records[-1]
    assert record.getMessage().startswith(f"sync for stream {stream.id}: 3.0")
    assert record.sync_delay == pytest.approx(3, abs=TOLERANCE)  # type: ignore[attr-defined]


async def test_a_reference_too_short_to_analyse_is_not_found(
    db: AsyncSession, cache: Redis, event: Event, settings: Settings, broadcast: Samples
) -> None:
    """The studio has only just started sending: a fraction of a second so far."""
    stream = await live_stream(db, event)
    await store_reference(cache, stream.id, np.zeros(100, dtype=np.float32), settings)
    result = await tv_sync.measure_delay(
        db, cache, stream.id, tv_features(broadcast), REFERENCE_START + 20, now=NOW
    )
    assert result.status is SyncStatus.NOT_FOUND
