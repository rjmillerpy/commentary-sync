import re
from collections.abc import Callable
from pathlib import Path

import pytest

from app.simulation.broadcast import SOURCE_SAMPLE_RATE
from app.sync import views
from app.sync.schema import Samples

AudioWriter = Callable[[str, Samples], Path]
QUERY_START_SECONDS = 12.5
QUERY_SECONDS = 10.0
FEED_DELAY_SECONDS = 5.0


def _slice(samples: Samples, start_seconds: float, length_seconds: float) -> Samples:
    start = int(start_seconds * SOURCE_SAMPLE_RATE)
    return samples[start : start + int(length_seconds * SOURCE_SAMPLE_RATE)]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.0, "00:00:00.000"),
        (75.25, "00:01:15.250"),
        (3723.5, "01:02:03.500"),
        (-4.2, "-00:00:04.200"),
    ],
    ids=["zero", "minutes", "hours", "negative"],
)
def test_format_clock(seconds: float, expected: str) -> None:
    assert views.format_clock(seconds) == expected


def test_locate_reports_the_position_of_a_matching_capture(
    broadcast: Samples, write_audio: AudioWriter, capsys: pytest.CaptureFixture[str]
) -> None:
    reference = write_audio("reference.m4a", broadcast)
    query = write_audio("query.m4a", _slice(broadcast, QUERY_START_SECONDS, QUERY_SECONDS))

    exit_code = views.main(["locate", str(reference), str(query)])

    output = capsys.readouterr().out
    assert exit_code == views.EXIT_MATCH
    assert "query starts at 00:00:12.5" in output
    assert output.rstrip().endswith("MATCH")
    assert "NO CONFIDENT MATCH" not in output


def test_locate_refuses_a_capture_of_another_broadcast(
    broadcast: Samples,
    other_broadcast: Samples,
    write_audio: AudioWriter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference = write_audio("reference.m4a", broadcast)
    query = write_audio("query.m4a", _slice(other_broadcast, QUERY_START_SECONDS, QUERY_SECONDS))

    exit_code = views.main(["locate", str(reference), str(query)])

    assert exit_code == views.EXIT_NO_MATCH
    assert "NO CONFIDENT MATCH" in capsys.readouterr().out


def test_compare_reports_the_delay_between_two_feeds(
    broadcast: Samples, write_audio: AudioWriter, capsys: pytest.CaptureFixture[str]
) -> None:
    feed_a = write_audio("feed_a.m4a", broadcast)
    feed_b = write_audio("feed_b.m4a", broadcast[int(FEED_DELAY_SECONDS * SOURCE_SAMPLE_RATE) :])

    exit_code = views.main(["compare", str(feed_a), str(feed_b), "--chunk", "8", "--step", "8"])

    output = capsys.readouterr().out
    median = re.search(r"median lag ([+-]\d+\.\d+)s", output)
    assert exit_code == views.EXIT_MATCH
    assert median is not None
    assert float(median.group(1)) == pytest.approx(FEED_DELAY_SECONDS, abs=0.05)
    assert "4 of 4 probes matched" in output
    assert "feed A is 5.0" in output and "behind feed B" in output


def test_compare_names_the_feed_that_is_behind_when_the_lag_is_negative(
    broadcast: Samples, write_audio: AudioWriter, capsys: pytest.CaptureFixture[str]
) -> None:
    feed_a = write_audio("feed_a.m4a", broadcast[int(FEED_DELAY_SECONDS * SOURCE_SAMPLE_RATE) :])
    feed_b = write_audio("feed_b.m4a", broadcast)

    views.main(["compare", str(feed_a), str(feed_b), "--chunk", "8", "--step", "8"])

    output = capsys.readouterr().out
    assert "feed B is 5.0" in output and "behind feed A" in output
    # Feed B's first seconds are not in feed A at all, so that probe must not match.
    assert "(no match)" in output


def test_compare_of_different_broadcasts_finds_nothing(
    broadcast: Samples,
    other_broadcast: Samples,
    write_audio: AudioWriter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    feed_a = write_audio("feed_a.m4a", broadcast)
    feed_b = write_audio("feed_b.m4a", other_broadcast)

    exit_code = views.main(["compare", str(feed_a), str(feed_b), "--chunk", "8", "--step", "8"])

    assert exit_code == views.EXIT_NO_MATCH
    assert "no confident matches" in capsys.readouterr().out


def test_missing_file_is_reported_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "missing.m4a")

    exit_code = views.main(["locate", missing, missing])

    captured = capsys.readouterr()
    assert exit_code == views.EXIT_ERROR
    assert captured.err.startswith("error: no such audio file")
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "arguments",
    [
        ["compare", "a.m4a", "b.m4a", "--chunk", "0.5"],
        ["compare", "a.m4a", "b.m4a", "--chunk", "500"],
        ["compare", "a.m4a", "b.m4a", "--step", "0"],
        ["compare", "a.m4a", "b.m4a", "--step", "abc"],
        ["locate", "only-one.m4a"],
        ["unknown-command"],
        [],
    ],
    ids=[
        "chunk-too-short",
        "chunk-too-long",
        "zero-step",
        "step-not-a-number",
        "missing-argument",
        "unknown-command",
        "no-command",
    ],
)
def test_invalid_arguments_exit_with_usage_error(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        views.main(arguments)
    assert raised.value.code == views.EXIT_ERROR
