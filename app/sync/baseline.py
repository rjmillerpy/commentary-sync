"""The baseline matcher: textbook normalised cross-correlation.

Slides the query along the reference, scores every position by the cosine
of the angle between the query and that window, and takes the best one, to
the nearest frame. It is confident when that peak stands far out of the
crowd of scores at every other position, as a robust z-score.
"""

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from app.sync.schema import Features, Match
from app.sync.service import FRAMES_PER_SECOND

# How far the peak must stand above the typical score, in robust standard
# deviations (median absolute deviations scaled to match one for normal data).
MIN_PEAK_Z = 8.0
MAD_TO_STD = 1.4826
# Positions within this of the peak belong to it; the rest are the crowd.
GUARD_SECONDS = 1.0
# Without this much crowd there is nothing to stand out from.
MIN_CROWD_SECONDS = 2.0
TINY = 1e-12

Scores = NDArray[np.float64]


class BaselineMatcher:
    """Normalised cross-correlation, to the nearest frame."""

    def locate_features(self, reference: Features, query: Features) -> Match:
        scores = _cosine_scores(reference, query)
        peak = int(np.argmax(scores))
        crowd = _crowd(scores, peak)
        score = float(scores[peak])
        if len(crowd) < MIN_CROWD_SECONDS * FRAMES_PER_SECOND:
            return Match(peak / FRAMES_PER_SECOND, score, peak_ratio=1.0, is_confident=False)
        spread = MAD_TO_STD * float(np.median(np.abs(crowd - np.median(crowd)))) + TINY
        peak_z = (score - float(np.median(crowd))) / spread
        return Match(
            offset_seconds=peak / FRAMES_PER_SECOND,
            score=score,
            peak_ratio=score / max(float(crowd.max()), TINY),
            is_confident=peak_z >= MIN_PEAK_Z,
        )


def _cosine_scores(reference: Features, query: Features) -> Scores:
    """The cosine between the query and each reference window, all bands at once."""
    query64 = query.astype(np.float64)
    reference64 = reference.astype(np.float64)
    dot = signal.correlate(reference64, query64, mode="valid", method="fft")[:, 0]
    energy = np.concatenate([[0.0], np.cumsum((reference64**2).sum(axis=1))])
    window_norm = np.sqrt(np.maximum(energy[len(query) :] - energy[: -len(query)], 0.0))
    query_norm = float(np.sqrt((query64**2).sum()))
    scores: Scores = dot / (window_norm * query_norm + TINY)
    return scores


def _crowd(scores: Scores, peak: int) -> Scores:
    guard = int(GUARD_SECONDS * FRAMES_PER_SECOND)
    return np.concatenate([scores[: max(0, peak - guard)], scores[peak + guard + 1 :]])
