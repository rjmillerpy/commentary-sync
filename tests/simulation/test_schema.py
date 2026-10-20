from dataclasses import FrozenInstanceError

import pytest

from app.simulation.schema import (
    BenchmarkConfig,
    BenchmarkReport,
    ConditionResult,
    NegativeControlResult,
)

CONDITION = ConditionResult(
    query_seconds=10.0,
    snr_db=0.0,
    trials=5,
    within_tolerance=5,
    confident=4,
    confident_but_wrong=0,
    median_error_seconds=0.015,
    p95_error_seconds=0.02,
    max_error_seconds=0.03,
)
CONTROL = NegativeControlResult(trials=10, false_confident=0, max_score=0.1)
REPORT = BenchmarkReport(conditions=(CONDITION,), negative_control=CONTROL)


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (BenchmarkConfig(), "trials"),
        (CONDITION, "confident"),
        (CONTROL, "false_confident"),
        (REPORT, "conditions"),
    ],
    ids=["config", "condition", "negative-control", "report"],
)
def test_value_objects_are_immutable(value: object, field: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, 0)


def test_default_config_covers_every_query_length_inside_the_reference() -> None:
    config = BenchmarkConfig()
    assert max(config.query_lengths_seconds) < config.reference_seconds
    assert config.trials > 0
