"""Command-line interface for the synthetic benchmark."""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace

from app.common.cli_arguments import bounded_number
from app.simulation import service
from app.simulation.schema import BenchmarkConfig, BenchmarkReport, ConditionResult

MIN_TRIALS = 1
MAX_TRIALS = 1000
MIN_REFERENCE_SECONDS = 40.0  # must hold the longest query plus margins
MAX_REFERENCE_SECONDS = 3600.0
MILLISECONDS_PER_SECOND = 1000
TABLE_HEADER = "query  SNR     within-tol  median     p95       max    confident  confident+wrong"


def build_parser() -> argparse.ArgumentParser:
    defaults = BenchmarkConfig()
    parser = argparse.ArgumentParser(
        prog="sync-benchmark", description="Benchmark sync accuracy on a synthetic broadcast."
    )
    parser.add_argument(
        "--trials", type=bounded_number(int, MIN_TRIALS, MAX_TRIALS), default=defaults.trials
    )
    parser.add_argument(
        "--reference-seconds",
        type=bounded_number(float, MIN_REFERENCE_SECONDS, MAX_REFERENCE_SECONDS),
        default=defaults.reference_seconds,
    )
    parser.add_argument("--seed", type=int, default=defaults.seed)
    return parser


def format_report(report: BenchmarkReport, config: BenchmarkConfig) -> str:
    tolerance_ms = config.tolerance_seconds * MILLISECONDS_PER_SECOND
    control = report.negative_control
    lines = [
        f"{config.trials} trials per row, tolerance {tolerance_ms:.0f} ms",
        TABLE_HEADER,
        *(_format_condition(condition) for condition in report.conditions),
        "",
        "negative control: queries from an unrelated broadcast",
        f"false confident matches: {control.false_confident}/{control.trials}"
        f"   (max score {control.max_score:.3f})",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = replace(
        BenchmarkConfig(),
        trials=args.trials,
        reference_seconds=args.reference_seconds,
        seed=args.seed,
    )
    print("building synthetic broadcast and running trials...")
    print(format_report(service.run_benchmark(config), config))
    return 0


def _format_condition(condition: ConditionResult) -> str:
    def milliseconds(seconds: float) -> str:
        return f"{seconds * MILLISECONDS_PER_SECOND:7.0f}ms"

    return (
        f"{condition.query_seconds:>4.0f}s {condition.snr_db:>+4.0f}dB  "
        f"{condition.within_tolerance:>4}/{condition.trials:<4} "
        f"{milliseconds(condition.median_error_seconds)} "
        f"{milliseconds(condition.p95_error_seconds)} "
        f"{milliseconds(condition.max_error_seconds)}   "
        f"{condition.confident:>4}/{condition.trials:<4}  {condition.confident_but_wrong:>6}"
    )


if __name__ == "__main__":
    sys.exit(main())
