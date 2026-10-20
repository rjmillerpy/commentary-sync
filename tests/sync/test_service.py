import numpy as np
import pytest

from app.sync import service
from app.sync.errors import InvalidAudioError
from app.sync.schema import LagProbe, Match, Samples

RATE = service.ANALYSIS_SAMPLE_RATE
QUERY_SECONDS = 8.0
ACCURACY_SECONDS = 0.02


def _slice(samples: Samples, start_seconds: float, length_seconds: float) -> Samples:
    start = int(start_seconds * RATE)
    return samples[start : start + int(length_seconds * RATE)]


def test_features_have_one_row_per_frame_and_one_column_per_band(
    analysis_broadcast: Samples,
) -> None:
    features = service.extract_features(analysis_broadcast)
    expected_frames = len(analysis_broadcast) / service.HOP_SAMPLES
    assert features.shape[1] == service.BAND_COUNT
    assert features.shape[0] == pytest.approx(expected_frames, rel=0.01)
    assert features.dtype == np.float32


@pytest.mark.parametrize("gain", [0.5, 0.05, 0.001], ids=["half", "phone-far-away", "very-quiet"])
def test_features_ignore_volume(analysis_broadcast: Samples, gain: float) -> None:
    """Regression: features changed with recording level.

    Band energies were floored at an absolute 1e-10, so quiet passages of a
    quiet recording hit the floor and produced different features (15% of
    values moved by more than 0.05 at a gain of 0.2). The floor is now relative
    to the recording's own mean level. Verify: any gain gives the same features.
    """
    loud = service.extract_features(analysis_broadcast)
    quiet = service.extract_features(analysis_broadcast * np.float32(gain))
    assert np.allclose(loud, quiet, atol=1e-3)


@pytest.mark.parametrize(
    ("reference_seconds", "query_seconds"),
    [(10.0, 0.5), (2.0, 5.0), (10.0, 0.01)],
    ids=["query-under-1s", "reference-shorter-than-query", "query-under-one-window"],
)
def test_unusable_lengths_are_rejected(
    analysis_broadcast: Samples, reference_seconds: float, query_seconds: float
) -> None:
    reference = _slice(analysis_broadcast, 0.0, reference_seconds)
    query = _slice(analysis_broadcast, 0.0, query_seconds)
    with pytest.raises(InvalidAudioError):
        service.locate(reference, query)


def test_track_lag_recovers_a_fixed_delay(analysis_broadcast: Samples) -> None:
    delay_seconds = 5.0
    feed_b = analysis_broadcast[int(delay_seconds * RATE) :]

    probes = list(
        service.track_lag(analysis_broadcast, feed_b, chunk_seconds=8.0, step_seconds=8.0)
    )
    summary = service.summarise_lag(probes)

    assert summary is not None
    assert summary.total_probes == len(probes) == 4
    assert summary.matched_probes == 4
    assert summary.median_lag_seconds == pytest.approx(delay_seconds, abs=ACCURACY_SECONDS)
    assert summary.spread_seconds < ACCURACY_SECONDS


@pytest.mark.parametrize(
    ("chunk_seconds", "step_seconds"),
    [(0.5, 10.0), (10.0, 0.0), (10.0, -1.0)],
    ids=["chunk-too-short", "zero-step", "negative-step"],
)
def test_track_lag_rejects_bad_probe_sizes(
    analysis_broadcast: Samples, chunk_seconds: float, step_seconds: float
) -> None:
    with pytest.raises(InvalidAudioError):
        list(
            service.track_lag(
                analysis_broadcast,
                analysis_broadcast,
                chunk_seconds=chunk_seconds,
                step_seconds=step_seconds,
            )
        )


def _unconfident_probe() -> LagProbe:
    match = Match(offset_seconds=1.0, score=0.1, peak_ratio=1.0, is_confident=False)
    return LagProbe(time_in_b_seconds=0.0, lag_seconds=1.0, match=match)


@pytest.mark.parametrize(
    "probes", [[], [_unconfident_probe()]], ids=["no-probes", "only-unconfident-probes"]
)
def test_summary_is_none_without_confident_probes(probes: list[LagProbe]) -> None:
    assert service.summarise_lag(probes) is None


def test_locate_uses_the_configured_matcher(analysis_broadcast: Samples) -> None:
    match = service.locate(analysis_broadcast, _slice(analysis_broadcast, 12.0, QUERY_SECONDS))
    assert match.offset_seconds == pytest.approx(12.0, abs=ACCURACY_SECONDS)
    assert match.is_confident
