import numpy as np
import pytest

from app.simulation import service
from app.simulation.broadcast import SOURCE_SAMPLE_RATE
from app.simulation.schema import BenchmarkConfig
from app.sync.service import ANALYSIS_SAMPLE_RATE

SMALL = BenchmarkConfig(
    reference_seconds=40.0,
    trials=4,
    query_lengths_seconds=(10.0,),
    snr_levels_db=(20.0,),
)


def test_to_analysis_rate_resamples() -> None:
    one_second = np.zeros(SOURCE_SAMPLE_RATE, dtype=np.float32)
    resampled = service.to_analysis_rate(one_second)
    assert len(resampled) == ANALYSIS_SAMPLE_RATE
    assert resampled.dtype == np.float32


@pytest.mark.parametrize("seed", [1, 2], ids=["seed-1", "seed-2"])
def test_quiet_room_captures_are_all_located(seed: int) -> None:
    """Integration: synthesise, encode, play into a room, locate."""
    config = BenchmarkConfig(
        reference_seconds=SMALL.reference_seconds,
        trials=SMALL.trials,
        query_lengths_seconds=SMALL.query_lengths_seconds,
        snr_levels_db=SMALL.snr_levels_db,
        seed=seed,
    )

    report = service.run_benchmark(config)

    (condition,) = report.conditions
    assert condition.trials == config.trials
    assert condition.within_tolerance == config.trials
    assert condition.confident_but_wrong == 0
    assert condition.max_error_seconds < config.tolerance_seconds
    assert condition.median_error_seconds <= condition.p95_error_seconds


def test_unrelated_broadcast_never_matches_confidently() -> None:
    report = service.run_benchmark(SMALL)
    control = report.negative_control
    assert control.trials == SMALL.trials * service.NEGATIVE_TRIALS_PER_TRIAL
    assert control.false_confident == 0


def test_one_condition_per_length_and_noise_level() -> None:
    config = BenchmarkConfig(
        reference_seconds=40.0,
        trials=1,
        query_lengths_seconds=(5.0, 10.0),
        snr_levels_db=(20.0, 0.0),
    )
    conditions = service.run_benchmark(config).conditions
    assert [(c.query_seconds, c.snr_db) for c in conditions] == [
        (5.0, 20.0),
        (5.0, 0.0),
        (10.0, 20.0),
        (10.0, 0.0),
    ]


def test_same_config_gives_the_same_report() -> None:
    assert service.run_benchmark(SMALL) == service.run_benchmark(SMALL)
