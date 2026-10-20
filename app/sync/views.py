"""Command-line interface for the sync domain: parse, call the service, print."""

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from app.common.cli_arguments import bounded_number
from app.sync import service
from app.sync.audio import decode_audio
from app.sync.errors import SyncError
from app.sync.schema import LagProbe, LagSummary

# Named, not __name__: run with `python -m` that is "__main__", which is
# outside `app` and so held to warnings (app.common.logs).
logger = logging.getLogger("app.sync.views")

EXIT_MATCH = 0
EXIT_NO_MATCH = 1
EXIT_ERROR = 2

MAX_CHUNK_SECONDS = 120.0
MAX_STEP_SECONDS = 3600.0
MIN_STEP_SECONDS = 1.0
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
MILLISECONDS_PER_SECOND = 1000


def format_clock(seconds: float) -> str:
    """Render seconds as [-]HH:MM:SS.mmm."""
    sign = "-" if seconds < 0 else ""
    total_minutes, remainder = divmod(abs(seconds), SECONDS_PER_MINUTE)
    hours, minutes = divmod(int(total_minutes), MINUTES_PER_HOUR)
    return f"{sign}{hours:02d}:{minutes:02d}:{remainder:06.3f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync-offset", description="Find how far one recording of a broadcast lags another."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    locate = commands.add_parser("locate", help="find a short capture inside a reference")
    locate.add_argument("reference", type=Path)
    locate.add_argument("query", type=Path)

    compare = commands.add_parser("compare", help="track the lag between two long recordings")
    compare.add_argument("feed_a", type=Path)
    compare.add_argument("feed_b", type=Path)
    compare.add_argument(
        "--chunk",
        type=bounded_number(float, service.MIN_QUERY_SECONDS, MAX_CHUNK_SECONDS),
        default=service.DEFAULT_CHUNK_SECONDS,
        help="seconds per probe",
    )
    compare.add_argument(
        "--step",
        type=bounded_number(float, MIN_STEP_SECONDS, MAX_STEP_SECONDS),
        default=service.DEFAULT_STEP_SECONDS,
        help="seconds between probes",
    )
    return parser


def run_locate(args: argparse.Namespace) -> int:
    reference = decode_audio(args.reference, service.ANALYSIS_SAMPLE_RATE)
    query = decode_audio(args.query, service.ANALYSIS_SAMPLE_RATE)
    match = service.locate(reference, query)
    print(f"query starts at {format_clock(match.offset_seconds)} into the reference")
    print(f"score {match.score:.3f}   peak/runner-up {match.peak_ratio:.2f}")
    if not match.is_confident:
        print("NO CONFIDENT MATCH (different feed, or too noisy)")
        return EXIT_NO_MATCH
    print("MATCH")
    return EXIT_MATCH


def run_compare(args: argparse.Namespace) -> int:
    feed_a = decode_audio(args.feed_a, service.ANALYSIS_SAMPLE_RATE)
    feed_b = decode_audio(args.feed_b, service.ANALYSIS_SAMPLE_RATE)
    probes = list(
        service.track_lag(feed_a, feed_b, chunk_seconds=args.chunk, step_seconds=args.step)
    )
    print(" time in B        lag     score  ratio")
    print("\n".join(_format_probe(probe) for probe in probes))
    summary = service.summarise_lag(probes)
    if summary is None:
        print("no confident matches: these look like different broadcasts")
        return EXIT_NO_MATCH
    print(_format_summary(summary))
    return EXIT_MATCH


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "locate": run_locate,
    "compare": run_compare,
}


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except SyncError as error:
        # The message is written for the user; the cause stays in the debug log.
        logger.debug("command %s failed", args.command, exc_info=True)
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR


def _format_probe(probe: LagProbe) -> str:
    flag = "" if probe.match.is_confident else "  (no match)"
    return (
        f"{format_clock(probe.time_in_b_seconds)}  {probe.lag_seconds:+9.3f}s  "
        f"{probe.match.score:.3f}  {probe.match.peak_ratio:5.2f}{flag}"
    )


def _format_summary(summary: LagSummary) -> str:
    lag = summary.median_lag_seconds
    behind, ahead = ("A", "B") if lag >= 0 else ("B", "A")
    return (
        f"\n{summary.matched_probes} of {summary.total_probes} probes matched: "
        f"median lag {lag:+.3f}s, "
        f"spread (max-min) {summary.spread_seconds * MILLISECONDS_PER_SECOND:.0f} ms\n"
        f"feed {behind} is {abs(lag):.3f}s behind feed {ahead}"
    )


if __name__ == "__main__":
    sys.exit(main())
