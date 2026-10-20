import numpy as np
import pytest

from app.sync import service
from app.sync.baseline import MIN_PEAK_Z, BaselineMatcher
from app.sync.schema import Features, Samples

RATE = service.ANALYSIS_SAMPLE_RATE
FRAME_SECONDS = 1 / service.FRAMES_PER_SECOND


def _features(samples: Samples, start_seconds: float, length_seconds: float) -> Features:
    start = int(start_seconds * RATE)
    return service.extract_features(samples[start : start + int(length_seconds * RATE)])


def test_offsets_are_whole_frames(analysis_broadcast: Samples) -> None:
    reference = service.extract_features(analysis_broadcast)
    match = BaselineMatcher().locate_features(reference, _features(analysis_broadcast, 7.0, 8.0))
    frames = match.offset_seconds / FRAME_SECONDS
    assert frames == pytest.approx(round(frames))


def test_a_match_stands_far_above_the_rest(analysis_broadcast: Samples) -> None:
    reference = service.extract_features(analysis_broadcast)
    match = BaselineMatcher().locate_features(reference, _features(analysis_broadcast, 7.0, 8.0))
    assert match.is_confident
    assert match.score == pytest.approx(1.0, abs=1e-3)
    assert match.peak_ratio > 1.0


def test_noise_never_stands_out_that_far() -> None:
    noise = np.random.default_rng(3).standard_normal(60 * RATE).astype(np.float32)
    other = np.random.default_rng(4).standard_normal(8 * RATE).astype(np.float32)
    match = BaselineMatcher().locate_features(
        service.extract_features(noise), service.extract_features(other)
    )
    assert not match.is_confident
    assert MIN_PEAK_Z > 1
