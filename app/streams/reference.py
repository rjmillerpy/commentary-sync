"""Each live stream's sync reference: the last few minutes of the
commentator's room audio, which includes their TV.

The studio records the commentator's microphone a second time, with echo
cancellation and noise suppression off so the TV in the background survives,
and sends it here in short chunks: 16-bit mono PCM at the matcher's 8 kHz,
stamped with the server time it was captured at. Listeners' TV recordings are
matched against it (service.measure_delay). It is never broadcast and never
logged, and it is trimmed to `sync_reference_seconds` as it grows.

Stored in Redis as a sorted set per stream, scored by capture time. The
app's Redis client decodes replies as text, so chunks are base64.
"""

import base64
import binascii
import uuid
from dataclasses import dataclass

import numpy as np
from redis.asyncio import Redis

from app.sync.schema import Samples
from app.sync.service import ANALYSIS_SAMPLE_RATE

KEY_PREFIX = "sync-reference:"
SAMPLE_RATE = ANALYSIS_SAMPLE_RATE
BYTES_PER_SAMPLE = 2  # signed 16-bit, little-endian
PCM_SCALE = 32768.0
MAX_CHUNK_SECONDS = 10
MAX_CHUNK_BYTES = MAX_CHUNK_SECONDS * SAMPLE_RATE * BYTES_PER_SAMPLE
# Kept a little past the window, then dropped with the stream's silence.
EXPIRY_GRACE_SECONDS = 60
MEMBER_SEPARATOR = ":"


@dataclass(frozen=True)
class ReferenceAudio:
    """The stored reference as one timeline: `samples` start at `start` (server time)."""

    start: float
    samples: Samples


def key(stream_id: uuid.UUID) -> str:
    return f"{KEY_PREFIX}{stream_id}"


async def add_chunk(
    cache: Redis,
    stream_id: uuid.UUID,
    captured_at: float,
    pcm: bytes,
    *,
    window_seconds: int,
    now: float,
) -> None:
    """Store one chunk and drop whatever has fallen out of the window."""
    member = f"{captured_at!r}{MEMBER_SEPARATOR}{base64.b64encode(pcm).decode()}"
    stream_key = key(stream_id)
    async with cache.pipeline(transaction=True) as pipe:
        pipe.zadd(stream_key, {member: captured_at})
        pipe.zremrangebyscore(stream_key, "-inf", now - window_seconds)
        pipe.expire(stream_key, window_seconds + EXPIRY_GRACE_SECONDS)
        await pipe.execute()


async def load(cache: Redis, stream_id: uuid.UUID) -> ReferenceAudio | None:
    """The stream's reference, or None if the studio has sent nothing."""
    members = await cache.zrange(key(stream_id), 0, -1)
    chunks = [chunk for chunk in (_parse(str(member)) for member in members) if chunk is not None]
    return assemble(chunks) if chunks else None


def assemble(chunks: list[tuple[float, bytes]]) -> ReferenceAudio:
    """Lay chunks out on one timeline by capture time. A gap (a dropped
    upload) stays silent, so everything after it keeps its true time."""
    ordered = sorted(chunks)
    start = ordered[0][0]
    pieces = [(round((at - start) * SAMPLE_RATE), _to_samples(pcm)) for at, pcm in ordered]
    length = max(offset + len(samples) for offset, samples in pieces)
    timeline = np.zeros(length, dtype=np.float32)
    for offset, samples in pieces:
        timeline[offset : offset + len(samples)] = samples  # an overlap: the later chunk wins
    return ReferenceAudio(start=start, samples=timeline)


def is_valid_pcm(pcm: bytes) -> bool:
    return 0 < len(pcm) <= MAX_CHUNK_BYTES and len(pcm) % BYTES_PER_SAMPLE == 0


def _to_samples(pcm: bytes) -> Samples:
    return (np.frombuffer(pcm, dtype="<i2").astype(np.float32) / PCM_SCALE).astype(np.float32)


def _parse(member: str) -> tuple[float, bytes] | None:
    """A stored chunk, or None for one that isn't ours."""
    captured_at, _, encoded = member.partition(MEMBER_SEPARATOR)
    try:
        return float(captured_at), base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None
