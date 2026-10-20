from dataclasses import FrozenInstanceError

import pytest

from app.sync.schema import LagProbe, LagSummary, Match

MATCH = Match(offset_seconds=1.5, score=0.4, peak_ratio=2.0, is_confident=True)
PROBE = LagProbe(time_in_b_seconds=30.0, lag_seconds=-4.2, match=MATCH)
SUMMARY = LagSummary(matched_probes=3, total_probes=4, median_lag_seconds=-4.2, spread_seconds=0.01)


@pytest.mark.parametrize(
    ("value", "field"),
    [(MATCH, "score"), (PROBE, "lag_seconds"), (SUMMARY, "matched_probes")],
    ids=["match", "lag-probe", "lag-summary"],
)
def test_value_objects_are_immutable(value: object, field: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, 0)


def test_probe_carries_its_match() -> None:
    assert PROBE.match is MATCH
