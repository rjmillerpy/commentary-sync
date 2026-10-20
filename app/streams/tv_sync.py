"""Syncing a listener to their TV by sound.

The commentator's studio sends its room audio, TV included, to the stream's
reference (reference.py). A listener's phone listens to their own TV for a
few seconds and sends the matcher's features of it (client/src/features.ts),
never the audio: 16 band energies 100 times a second, from which the sound
can't be played back or the words recovered. The matcher (app/sync) finds
that moment in the reference. Both are stamped in server time, so where it
was found says how far apart the two TVs are:

    delay = when the listener's TV played it - when the commentator's TV did

which is the delay to play the commentary at. Nothing about the game clock is
used, so stoppages, resets and broken clocks don't matter.

Features are matched in memory and discarded: never stored, never logged.
Matching is CPU work, so it runs off the event loop.
"""

import asyncio
import logging
import uuid
from datetime import datetime

import numpy as np
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.common.config import Settings
from app.streams import reference, service
from app.streams.errors import CaptureTimeError, SyncAudioError
from app.streams.schema import SyncResult, SyncStatus
from app.sync.errors import InvalidAudioError
from app.sync.schema import Features, Samples
from app.sync.service import BAND_COUNT, FRAMES_PER_SECOND, extract_features, locate_features

logger = logging.getLogger(__name__)

# A capture stamped more than this far in the past, or at all in the future
# (beyond clock jitter), isn't a recording of now.
MAX_CAPTURE_AGE_SECONDS = 120.0
MAX_CAPTURE_LEAD_SECONDS = 5.0
MIN_RECORDING_SECONDS = 3.0
MAX_RECORDING_SECONDS = 20.0
BYTES_PER_VALUE = 4  # float32, little-endian
FRAME_BYTES = BAND_COUNT * BYTES_PER_VALUE
MIN_FEATURE_FRAMES = int(MIN_RECORDING_SECONDS * FRAMES_PER_SECOND) - 10  # the STFT's edges
MAX_FEATURE_FRAMES = int(MAX_RECORDING_SECONDS * FRAMES_PER_SECOND)
MAX_FEATURE_BYTES = MAX_FEATURE_FRAMES * FRAME_BYTES


async def add_reference(
    db: AsyncSession,
    cache: Redis,
    user: User,
    stream_id: uuid.UUID,
    captured_at: float,
    pcm: bytes,
    settings: Settings,
    *,
    now: datetime,
) -> None:
    """Add a chunk of the commentator's room audio to their live stream's reference."""
    stream = await service.own_live_stream(db, user, stream_id)
    _check_capture_time(captured_at, now)
    if not reference.is_valid_pcm(pcm):
        raise SyncAudioError("reference chunks are 16-bit PCM, up to 10 s")
    await reference.add_chunk(
        cache,
        stream.id,
        captured_at,
        pcm,
        window_seconds=settings.sync_reference_seconds,
        now=now.timestamp(),
    )


async def measure_delay(
    db: AsyncSession,
    cache: Redis,
    stream_id: uuid.UUID,
    features: bytes,
    captured_at: float,
    *,
    now: datetime,
) -> SyncResult:
    """How far the listener's TV, in `features` of what the phone heard, is
    behind the commentator's."""
    stream = await service.live_stream(db, stream_id)
    _check_capture_time(captured_at, now)
    query = _read_features(features)
    stored = await reference.load(cache, stream.id)
    reference_features = (
        None if stored is None else await asyncio.to_thread(_features_of, stored.samples)
    )
    if stored is None or reference_features is None or len(reference_features) < len(query):
        return _not_found(stream.id, "reference too short")
    match = await asyncio.to_thread(locate_features, reference_features, query)
    if not match.is_confident:
        return _not_found(stream.id, "no confident match")
    delay = captured_at - (stored.start + match.offset_seconds)
    logger.info(
        "sync for stream %s: %.2f s",
        stream.id,
        delay,
        extra={"stream_id": str(stream.id), "sync_delay": delay, "peak_ratio": match.peak_ratio},
    )
    return SyncResult(status=SyncStatus.MATCHED, delay_seconds=delay, peak_ratio=match.peak_ratio)


def _read_features(data: bytes) -> Features:
    """The phone's features: frames of BAND_COUNT float32 values, row by row."""
    if len(data) % FRAME_BYTES != 0:
        raise SyncAudioError(f"features come in frames of {BAND_COUNT} float32 values")
    frames = len(data) // FRAME_BYTES
    if not MIN_FEATURE_FRAMES <= frames <= MAX_FEATURE_FRAMES:
        raise SyncAudioError(
            f"features must cover {MIN_RECORDING_SECONDS:.0f} to {MAX_RECORDING_SECONDS:.0f} s"
        )
    features = np.frombuffer(data, dtype="<f4").reshape(frames, BAND_COUNT)
    if not np.isfinite(features).all():
        raise SyncAudioError("features must be finite numbers")
    return features


def _features_of(samples: Samples) -> Features | None:
    """The reference's features, or None if there is too little audio yet."""
    try:
        return extract_features(samples)
    except InvalidAudioError:
        return None


def _check_capture_time(captured_at: float, now: datetime) -> None:
    age = now.timestamp() - captured_at
    if not -MAX_CAPTURE_LEAD_SECONDS <= age <= MAX_CAPTURE_AGE_SECONDS:
        raise CaptureTimeError(f"capture time is {age:.0f} s from the server's clock")


def _not_found(stream_id: uuid.UUID, why: str) -> SyncResult:
    logger.info(
        "sync for stream %s: not found (%s)",
        stream_id,
        why,
        extra={"stream_id": str(stream_id), "sync_outcome": "not_found"},
    )
    return SyncResult(status=SyncStatus.NOT_FOUND)
