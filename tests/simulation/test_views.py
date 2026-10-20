import pytest

from app.simulation import views
from app.simulation.schema import (
    BenchmarkConfig,
    BenchmarkReport,
    ConditionResult,
    NegativeControlResult,
)


def test_report_shows_one_row_per_condition_and_the_negative_control() -> None:
    condition = ConditionResult(
        query_seconds=10.0,
        snr_db=-5.0,
        trials=25,
        within_tolerance=16,
        confident=1,
        confident_but_wrong=0,
        median_error_seconds=0.018,
        p95_error_seconds=59.05,
        max_error_seconds=83.913,
    )
    report = BenchmarkReport(
        conditions=(condition,),
        negative_control=NegativeControlResult(trials=50, false_confident=0, max_score=0.146),
    )

    text = views.format_report(report, BenchmarkConfig())

    assert "25 trials per row, tolerance 200 ms" in text
    assert "10s   -5dB" in text
    assert "16/25" in text
    assert "18ms" in text and "83913ms" in text
    assert "false confident matches: 0/50   (max score 0.146)" in text


def test_smoke_full_run_prints_every_condition(capsys: pytest.CaptureFixture[str]) -> None:
    """Smoke: the whole benchmark runs end to end from the command line."""
    exit_code = views.main(["--trials", "1", "--reference-seconds", "40", "--seed", "3"])

    output = capsys.readouterr().out
    defaults = BenchmarkConfig()
    expected_rows = len(defaults.query_lengths_seconds) * len(defaults.snr_levels_db)
    assert exit_code == 0
    assert output.count("dB") == expected_rows
    assert "false confident matches: 0/2" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--trials", "0"],
        ["--trials", "1001"],
        ["--trials", "many"],
        ["--reference-seconds", "5"],
        ["--seed", "x"],
    ],
    ids=[
        "zero-trials",
        "too-many-trials",
        "trials-not-a-number",
        "reference-too-short",
        "bad-seed",
    ],
)
def test_invalid_arguments_exit_with_usage_error(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        views.main(arguments)
    assert raised.value.code == 2
