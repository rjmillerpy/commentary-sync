"""Value objects and array types for the sync domain."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# Mono audio samples in the range -1..1.
Samples = NDArray[np.float32]
# Time-differenced log band energies, shape (frames, bands).
Features = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class Match:
    """Where a query was found inside a reference, and how sure we are."""

    offset_seconds: float
    score: float  # normalised correlation at the peak, 0..1
    peak_ratio: float  # peak / best peak elsewhere; about 1 means ambiguous
    is_confident: bool


@dataclass(frozen=True, slots=True)
class LagProbe:
    """One chunk of feed B located inside feed A."""

    time_in_b_seconds: float
    lag_seconds: float  # position in A minus position in B
    match: Match


@dataclass(frozen=True, slots=True)
class LagSummary:
    """The lag between two feeds across every confident probe."""

    matched_probes: int
    total_probes: int
    median_lag_seconds: float
    spread_seconds: float  # largest lag minus smallest lag
