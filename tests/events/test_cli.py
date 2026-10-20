from collections.abc import Callable

import httpx2
import pytest

from app.common.config import Settings
from app.events import cli
from tests.events.conftest import FakeEspn

DAY = "2026-10-18"


def run(argv: list[str], factory: Callable[[float], httpx2.AsyncClient]) -> int:
    return cli.main(argv, http_client_factory=factory)


def test_imports_a_league_and_prints_the_summary(
    migrated_settings: Settings,
    http_client_factory: Callable[[float], httpx2.AsyncClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(["--league", "nfl", "--start", DAY, "--days", "1"], http_client_factory) == 0
    assert capsys.readouterr().out.strip() == (
        "nfl: 12 events over 1 days from 2026-10-18: 12 new, 0 updated"
    )


def test_second_run_updates(
    migrated_settings: Settings,
    http_client_factory: Callable[[float], httpx2.AsyncClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(["--league", "nfl", "--start", DAY, "--days", "1"], http_client_factory)
    run(["--league", "nfl", "--start", DAY, "--days", "1"], http_client_factory)
    assert capsys.readouterr().out.strip().endswith("0 new, 12 updated")


def test_defaults_to_seven_days_from_today(
    migrated_settings: Settings,
    http_client_factory: Callable[[float], httpx2.AsyncClient],
    fake_espn: FakeEspn,
) -> None:
    assert run(["--league", "nba"], http_client_factory) == 0
    assert len(fake_espn.requests) == cli.DEFAULT_DAYS


def test_provider_failure_exits_2_with_a_message(
    migrated_settings: Settings,
    http_client_factory: Callable[[float], httpx2.AsyncClient],
    fake_espn: FakeEspn,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_espn.override = lambda _: httpx2.Response(404)
    assert run(["--league", "nfl", "--start", DAY, "--days", "1"], http_client_factory) == 2
    assert capsys.readouterr().err.startswith("error: ESPN answered 404")


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--league", "mlb"],
        ["--league", "nfl", "--days", "0"],
        ["--league", "nfl", "--days", "32"],
        ["--league", "nfl", "--start", "18/10/2026"],
    ],
    ids=["no-league", "unknown-league", "zero-days", "too-many-days", "bad-date"],
)
def test_rejects_bad_arguments(
    argv: list[str], http_client_factory: Callable[[float], httpx2.AsyncClient]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run(argv, http_client_factory)
    assert exit_info.value.code == 2
