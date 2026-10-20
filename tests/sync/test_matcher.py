"""Loading matchers, and the contract every installed matcher must meet."""

import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from app.sync import matcher, service
from app.sync.errors import MatcherNotFoundError
from app.sync.schema import Samples

RATE = service.ANALYSIS_SAMPLE_RATE
QUERY_SECONDS = 8.0
ACCURACY_SECONDS = 0.02
FAKE_ENTRY_POINTS = """[commentary_sync.matchers]
fake = fake_matcher:FakeMatcher
"""
FAKE_MODULE = """from app.sync.baseline import BaselineMatcher


class FakeMatcher(BaselineMatcher):
    pass
"""


def _slice(samples: Samples, start_seconds: float, length_seconds: float) -> Samples:
    start = int(start_seconds * RATE)
    return samples[start : start + int(length_seconds * RATE)]


@pytest.fixture
def fresh_registry() -> Iterator[None]:
    """Entry points are read once per process; tests that install one re-read them."""
    matcher._registered.cache_clear()
    yield
    matcher._registered.cache_clear()


@pytest.fixture
def fake_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fresh_registry: None) -> None:
    """A real installed distribution registering a matcher named `fake`."""
    (tmp_path / "fake_matcher.py").write_text(FAKE_MODULE)
    dist_info = tmp_path / "fake_matcher-1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text("Metadata-Version: 2.1\nName: fake-matcher\nVersion: 1.0\n")
    (dist_info / "entry_points.txt").write_text(FAKE_ENTRY_POINTS)
    monkeypatch.syspath_prepend(str(tmp_path))


def test_the_baseline_is_always_available() -> None:
    assert matcher.BASELINE in matcher.available()


def test_the_configured_matcher_is_loaded(
    fake_installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COMMENTARY_SYNC_MATCHER", "fake")
    assert type(matcher.load()).__name__ == "FakeMatcher"


def test_a_missing_matcher_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: a deployment pinned to a matcher that isn't installed
    must not quietly fall back to the baseline."""
    monkeypatch.setenv("COMMENTARY_SYNC_MATCHER", "not_installed")
    with pytest.raises(MatcherNotFoundError, match="not_installed"):
        matcher.load()


def test_unset_uses_the_only_other_matcher_else_the_baseline(
    fake_installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COMMENTARY_SYNC_MATCHER")
    others = [name for name in matcher.available() if name != matcher.BASELINE]
    assert matcher.default_name() == (others[0] if len(others) == 1 else matcher.BASELINE)
    assert "fake" in others


def test_an_explicit_name_wins_over_the_setting() -> None:
    assert type(matcher.load(matcher.BASELINE)).__name__ == "BaselineMatcher"


# The contract: every installed matcher, the baseline included.
INSTALLED = matcher.available()


@pytest.fixture(params=INSTALLED, ids=INSTALLED)
def each_matcher(request: pytest.FixtureRequest) -> matcher.Matcher:
    found: matcher.Matcher = matcher.load(request.param)
    return found


@pytest.mark.parametrize(
    "true_offset", [3.0, 12.34, 25.5], ids=["near-start", "between-frames", "near-end"]
)
def test_contract_locates_a_clean_slice(
    each_matcher: matcher.Matcher, analysis_broadcast: Samples, true_offset: float
) -> None:
    reference = service.extract_features(analysis_broadcast)
    query = service.extract_features(_slice(analysis_broadcast, true_offset, QUERY_SECONDS))
    match = each_matcher.locate_features(reference, query)
    assert match.offset_seconds == pytest.approx(true_offset, abs=ACCURACY_SECONDS)
    assert match.is_confident


def test_contract_silence_is_not_a_match(
    each_matcher: matcher.Matcher, analysis_broadcast: Samples
) -> None:
    silence = np.zeros(int(QUERY_SECONDS * RATE), dtype=np.float32)
    reference = service.extract_features(analysis_broadcast)
    match = each_matcher.locate_features(reference, service.extract_features(silence))
    assert np.isfinite(match.score)
    assert not match.is_confident


def test_contract_unrelated_audio_is_not_a_confident_match(
    each_matcher: matcher.Matcher, analysis_broadcast: Samples, other_broadcast: Samples
) -> None:
    from app.simulation.service import to_analysis_rate

    query = _slice(to_analysis_rate(other_broadcast), 10.0, QUERY_SECONDS)
    reference = service.extract_features(analysis_broadcast)
    match = each_matcher.locate_features(reference, service.extract_features(query))
    assert not match.is_confident


def test_contract_no_confidence_without_somewhere_else_to_compare(
    each_matcher: matcher.Matcher, analysis_broadcast: Samples
) -> None:
    """Regression: a reference barely longer than the query has no rival peak.

    The first prototype reported an infinite peak ratio here and so called any
    such match confident. Verify: the ratio is 1.0 and the match is not confident.
    """
    reference = service.extract_features(_slice(analysis_broadcast, 0.0, QUERY_SECONDS + 0.5))
    query = service.extract_features(_slice(analysis_broadcast, 0.2, QUERY_SECONDS))
    match = each_matcher.locate_features(reference, query)
    assert match.peak_ratio == 1.0
    assert not match.is_confident


def test_contract_locating_in_a_ten_minute_reference_is_fast(
    each_matcher: matcher.Matcher,
) -> None:
    """Performance: one lookup must stay far below the capture length it serves."""
    reference = np.random.default_rng(1).standard_normal(600 * RATE).astype(np.float32)
    reference_features = service.extract_features(reference)
    query_features = service.extract_features(_slice(reference, 300.0, 10.0))

    started = time.perf_counter()
    match = each_matcher.locate_features(reference_features, query_features)
    elapsed = time.perf_counter() - started

    assert match.offset_seconds == pytest.approx(300.0, abs=ACCURACY_SECONDS)
    assert elapsed < 5.0
