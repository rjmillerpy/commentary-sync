import io
from pathlib import Path

import numpy as np
import pytest

from app.sync.audio import decode_audio, encode_aac
from app.sync.errors import AudioDecodeError, AudioEncodeError
from app.sync.schema import Samples

SOURCE_RATE = 16000
TARGET_RATE = 8000
TONE_HZ = 440.0
TONE_SECONDS = 2.0
BIT_RATE = 64_000


@pytest.fixture
def tone() -> Samples:
    time = np.arange(int(TONE_SECONDS * SOURCE_RATE)) / SOURCE_RATE
    return (0.5 * np.sin(2 * np.pi * TONE_HZ * time)).astype(np.float32)


def _dominant_frequency(samples: Samples, sample_rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(samples))
    return float(np.fft.rfftfreq(len(samples), 1 / sample_rate)[np.argmax(spectrum)])


def test_file_roundtrip_resamples_and_keeps_the_signal(tone: Samples, tmp_path: Path) -> None:
    path = tmp_path / "tone.m4a"
    encode_aac(tone, SOURCE_RATE, path, bit_rate=BIT_RATE)

    decoded = decode_audio(path, TARGET_RATE)

    assert decoded.dtype == np.float32
    assert len(decoded) == pytest.approx(TONE_SECONDS * TARGET_RATE, rel=0.1)
    assert _dominant_frequency(decoded, TARGET_RATE) == pytest.approx(TONE_HZ, abs=2.0)


def test_stream_roundtrip(tone: Samples) -> None:
    buffer = io.BytesIO()
    encode_aac(tone, SOURCE_RATE, buffer, bit_rate=BIT_RATE, container_format="adts")
    buffer.seek(0)

    decoded = decode_audio(buffer, SOURCE_RATE, container_format="aac")

    assert len(decoded) == pytest.approx(len(tone), rel=0.1)


def _missing(tmp_path: Path) -> Path:
    return tmp_path / "missing.m4a"


def _directory(tmp_path: Path) -> Path:
    return tmp_path


def _garbage(tmp_path: Path) -> Path:
    path = tmp_path / "garbage.m4a"
    path.write_bytes(b"this is not audio" * 200)
    return path


def _empty(tmp_path: Path) -> Path:
    path = tmp_path / "empty.m4a"
    path.touch()
    return path


@pytest.mark.parametrize(
    "make_source",
    [_missing, _directory, _garbage, _empty],
    ids=["missing-file", "directory", "garbage-bytes", "empty-file"],
)
def test_unreadable_sources_raise_a_domain_error(make_source: object, tmp_path: Path) -> None:
    assert callable(make_source)
    with pytest.raises(AudioDecodeError) as raised:
        decode_audio(make_source(tmp_path), TARGET_RATE)
    # Rule 10: the message names the file, never the decoder's internals.
    assert "Errno" not in str(raised.value)


def test_audio_over_the_length_cap_is_refused(tone: Samples, tmp_path: Path) -> None:
    path = tmp_path / "tone.m4a"
    encode_aac(tone, SOURCE_RATE, path, bit_rate=BIT_RATE)

    with pytest.raises(AudioDecodeError, match="longer than"):
        decode_audio(path, TARGET_RATE, max_seconds=0.5)


def test_decode_error_keeps_the_original_cause(tmp_path: Path) -> None:
    with pytest.raises(AudioDecodeError) as raised:
        decode_audio(_garbage(tmp_path), TARGET_RATE)
    assert raised.value.__cause__ is not None


def test_writing_to_a_missing_directory_raises_a_domain_error(
    tone: Samples, tmp_path: Path
) -> None:
    with pytest.raises(AudioEncodeError):
        encode_aac(tone, SOURCE_RATE, tmp_path / "no-such-dir" / "tone.m4a", bit_rate=BIT_RATE)
