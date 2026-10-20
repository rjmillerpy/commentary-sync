"""Read and write audio files: the file-system boundary of the sync domain."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

import av
import av.container
import av.error
import numpy as np

from app.sync.errors import AudioDecodeError, AudioEncodeError
from app.sync.schema import Samples

logger = logging.getLogger(__name__)

MAX_AUDIO_SECONDS = 4 * 60 * 60  # longer than any single broadcast we expect
AAC_CODEC = "aac"
MONO_LAYOUT = "mono"
PACKED_FLOAT_FORMAT = "flt"
PLANAR_FLOAT_FORMAT = "fltp"


def decode_audio(
    source: Path | BinaryIO,
    sample_rate: int,
    *,
    container_format: str | None = None,
    max_seconds: float = MAX_AUDIO_SECONDS,
) -> Samples:
    """Decode any ffmpeg-readable audio to mono float32 at sample_rate."""
    label = str(source) if isinstance(source, Path) else "audio stream"
    if isinstance(source, Path) and not source.is_file():
        raise AudioDecodeError(f"no such audio file: {label}")

    max_samples = int(max_seconds * sample_rate)
    opened = str(source) if isinstance(source, Path) else source
    try:
        with av.open(opened, "r", format=container_format) as container:
            samples = _collect_bounded(_iter_resampled(container, sample_rate), max_samples)
    except (av.error.FFmpegError, OSError) as error:
        logger.warning("audio decode failed for %s: %s", label, type(error).__name__)
        raise AudioDecodeError(f"could not decode audio from {label}") from error

    if samples is None:
        raise AudioDecodeError(f"{label} is longer than {max_seconds:.0f} s")
    if len(samples) == 0:
        raise AudioDecodeError(f"{label} contains no audio")
    return samples


def encode_aac(
    samples: Samples,
    sample_rate: int,
    target: Path | BinaryIO,
    *,
    bit_rate: int,
    container_format: str | None = None,
) -> None:
    """Write mono samples as AAC. The container is taken from the file suffix
    unless container_format is given."""
    frame = av.AudioFrame.from_ndarray(
        samples[np.newaxis, :].astype(np.float32), format=PLANAR_FLOAT_FORMAT, layout=MONO_LAYOUT
    )
    frame.sample_rate = sample_rate
    label = str(target) if isinstance(target, Path) else "audio stream"
    opened = str(target) if isinstance(target, Path) else target
    try:
        with av.open(opened, "w", format=container_format) as container:
            stream = container.add_stream(AAC_CODEC, rate=sample_rate)
            if not isinstance(stream, av.AudioStream):
                raise AudioEncodeError(f"{AAC_CODEC} did not produce an audio stream")
            stream.bit_rate = bit_rate
            for packet in (*stream.encode(frame), *stream.encode(None)):
                container.mux(packet)
    except (av.error.FFmpegError, OSError) as error:
        logger.warning("audio encode failed for %s: %s", label, type(error).__name__)
        raise AudioEncodeError(f"could not write audio to {label}") from error


def _iter_resampled(container: av.container.InputContainer, sample_rate: int) -> Iterator[Samples]:
    if not container.streams.audio:
        return
    resampler = av.AudioResampler(format=PACKED_FLOAT_FORMAT, layout=MONO_LAYOUT, rate=sample_rate)
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            yield _to_samples(resampled)
    for flushed in resampler.resample(None):
        yield _to_samples(flushed)


def _to_samples(frame: av.AudioFrame) -> Samples:
    return np.asarray(frame.to_ndarray(), dtype=np.float32).reshape(-1)


def _collect_bounded(chunks: Iterator[Samples], max_samples: int) -> Samples | None:
    """Join chunks into one array, or return None once they exceed max_samples."""
    collected: list[Samples] = []
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > max_samples:
            return None
        collected.append(chunk)
    if not collected:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(collected).astype(np.float32)
