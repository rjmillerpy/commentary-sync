"""Locate a short audio capture inside a longer reference recording.

The reference is the game audio as the commentator heard it; the query is a
few seconds of the same broadcast picked up by a viewer's microphone. Where the
query sits in the reference tells us how far the viewer is behind.
"""

from collections.abc import Iterator, Sequence
from itertools import pairwise

import numpy as np
from scipy import signal

from app.sync import matcher
from app.sync.errors import InvalidAudioError
from app.sync.schema import Features, LagProbe, LagSummary, Match, Samples

# A TV speaker heard by a phone mic carries little above 4 kHz.
ANALYSIS_SAMPLE_RATE = 8000
HOP_SAMPLES = 80  # 10 ms
WINDOW_SAMPLES = 256  # 32 ms
FRAMES_PER_SECOND = ANALYSIS_SAMPLE_RATE / HOP_SAMPLES
BAND_COUNT = 16
BAND_LOW_HZ = 300.0
BAND_HIGH_HZ = 3600.0
DELTA_FRAMES = 2  # frames between the two log energies that are differenced

MIN_QUERY_SECONDS = 1.0
DEFAULT_CHUNK_SECONDS = 10.0
DEFAULT_STEP_SECONDS = 30.0

# Band energies are floored relative to the recording's own mean level, so the
# features do not depend on how loud the recording is.
RELATIVE_ENERGY_FLOOR = 1e-2
SILENCE_FLOOR = 1e-30  # keeps the log finite when the whole recording is silent


def extract_features(samples: Samples) -> Features:
    """Time-differenced log band energies, shape (frames, bands).

    Differencing in time cancels anything constant per band (volume, speaker
    and microphone EQ), so the same broadcast heard through different gear
    still produces similar features.
    """
    min_samples = WINDOW_SAMPLES + DELTA_FRAMES * HOP_SAMPLES
    if len(samples) < min_samples:
        raise InvalidAudioError(f"audio is too short to analyse ({len(samples)} samples)")

    frequencies, _, spectrum = signal.stft(
        samples,
        fs=ANALYSIS_SAMPLE_RATE,
        nperseg=WINDOW_SAMPLES,
        noverlap=WINDOW_SAMPLES - HOP_SAMPLES,
        boundary=None,
        padded=False,
    )
    power = np.abs(spectrum) ** 2
    edges = np.geomspace(BAND_LOW_HZ, BAND_HIGH_HZ, BAND_COUNT + 1)
    band_energy = np.stack(
        [
            power[(frequencies >= low) & (frequencies < high)].sum(axis=0)
            for low, high in pairwise(edges)
        ]
    )
    floor = RELATIVE_ENERGY_FLOOR * float(band_energy.mean()) + SILENCE_FLOOR
    log_energy = np.log(band_energy + floor)
    delta = log_energy[:, DELTA_FRAMES:] - log_energy[:, :-DELTA_FRAMES]
    return np.asarray(delta.T, dtype=np.float32)


def locate_features(reference: Features, query: Features) -> Match:
    """Find the query's position in the reference with the configured matcher."""
    if len(query) < MIN_QUERY_SECONDS * FRAMES_PER_SECOND:
        raise InvalidAudioError(f"query must be at least {MIN_QUERY_SECONDS:.0f} s long")
    if len(reference) < len(query):
        raise InvalidAudioError("reference is shorter than the query")
    return matcher.load().locate_features(reference, query)


def locate(reference: Samples, query: Samples) -> Match:
    return locate_features(extract_features(reference), extract_features(query))


def track_lag(
    feed_a: Samples,
    feed_b: Samples,
    *,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
    step_seconds: float = DEFAULT_STEP_SECONDS,
) -> Iterator[LagProbe]:
    """Locate successive chunks of feed B inside feed A.

    A steady lag means the feeds hold a fixed distance apart. A jump means a
    pause, a rebuffer or a differing ad break.
    """
    if chunk_seconds < MIN_QUERY_SECONDS or step_seconds <= 0:
        raise InvalidAudioError("chunk and step must be positive, chunk at least 1 s")

    features_a = extract_features(feed_a)
    chunk_samples = int(chunk_seconds * ANALYSIS_SAMPLE_RATE)
    step_samples = int(step_seconds * ANALYSIS_SAMPLE_RATE)
    for start in range(0, len(feed_b) - chunk_samples + 1, step_samples):
        chunk_features = extract_features(feed_b[start : start + chunk_samples])
        match = locate_features(features_a, chunk_features)
        time_in_b = start / ANALYSIS_SAMPLE_RATE
        yield LagProbe(
            time_in_b_seconds=time_in_b,
            lag_seconds=match.offset_seconds - time_in_b,
            match=match,
        )


def summarise_lag(probes: Sequence[LagProbe]) -> LagSummary | None:
    """Median lag and its spread over the confident probes; None if there are none."""
    lags = np.array([probe.lag_seconds for probe in probes if probe.match.is_confident])
    if len(lags) == 0:
        return None
    return LagSummary(
        matched_probes=len(lags),
        total_probes=len(probes),
        median_lag_seconds=float(np.median(lags)),
        spread_seconds=float(np.ptp(lags)),
    )
