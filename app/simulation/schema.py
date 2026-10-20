"""Value objects for the synthetic sync benchmark."""

from dataclasses import dataclass

from app.sync.schema import Features, Samples


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    reference_seconds: float = 180.0
    trials: int = 25
    tolerance_seconds: float = 0.2
    query_lengths_seconds: tuple[float, ...] = (3.0, 5.0, 10.0, 20.0)
    snr_levels_db: tuple[float, ...] = (20.0, 10.0, 0.0, -5.0, -10.0)
    seed: int = 7


@dataclass(frozen=True, slots=True)
class Scenario:
    """One broadcast as the commentator and a viewer each receive it."""

    reference_features: Features  # the commentator's side, already analysed
    viewer_feed: Samples  # the viewer's side, at the source sample rate
    babble: Samples  # people talking in the viewer's room


@dataclass(frozen=True, slots=True)
class ConditionResult:
    """Accuracy over every trial at one query length and noise level."""

    query_seconds: float
    snr_db: float
    trials: int
    within_tolerance: int
    confident: int
    confident_but_wrong: int  # the dangerous case: sure of a wrong position
    median_error_seconds: float
    p95_error_seconds: float
    max_error_seconds: float


@dataclass(frozen=True, slots=True)
class NegativeControlResult:
    """Queries from an unrelated broadcast; none should match confidently."""

    trials: int
    false_confident: int
    max_score: float


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    conditions: tuple[ConditionResult, ...]
    negative_control: NegativeControlResult
