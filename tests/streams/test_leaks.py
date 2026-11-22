"""The leak-detector seam: loading one, and the public build's own."""

import uuid
from collections.abc import Iterator
from importlib.metadata import EntryPoint
from pathlib import Path

import numpy as np
import pytest
from fastapi import BackgroundTasks
from redis.asyncio import Redis

from app.streams import leaks
from app.streams.hls_audio import HlsReader
from app.streams.leaks import ListenerTv, NoLeakDetector, get_leak_detector
from app.streams.models import Stream
from app.streams.schema import GameAudio

pytestmark = pytest.mark.anyio

FAKE_MODULE = """from app.streams.leaks import NoLeakDetector


class FakeDetector(NoLeakDetector):
    pass
"""


@pytest.fixture
def fresh_detector() -> Iterator[None]:
    """The detector is loaded once per process; tests that change what's installed reload it."""
    leaks.detector.cache_clear()
    yield
    leaks.detector.cache_clear()


def installed(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    points = [
        EntryPoint(name, "fake_detector:FakeDetector", leaks.ENTRY_POINT_GROUP) for name in names
    ]
    monkeypatch.setattr(
        leaks, "entry_points", lambda group: points if group == leaks.ENTRY_POINT_GROUP else []
    )


@pytest.fixture
def fake_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "fake_detector.py").write_text(FAKE_MODULE)
    monkeypatch.syspath_prepend(str(tmp_path))


def test_with_none_installed_nothing_is_checked(
    monkeypatch: pytest.MonkeyPatch, fresh_detector: None
) -> None:
    installed(monkeypatch)
    assert isinstance(get_leak_detector(), NoLeakDetector)


def test_an_installed_detector_is_used(
    monkeypatch: pytest.MonkeyPatch, fresh_detector: None, fake_module: None
) -> None:
    installed(monkeypatch, "fake")
    assert type(get_leak_detector()).__name__ == "FakeDetector"


def test_with_several_installed_the_first_by_name_is_used_and_it_says_so(
    monkeypatch: pytest.MonkeyPatch,
    fresh_detector: None,
    fake_module: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    installed(monkeypatch, "zeta", "alpha")
    assert type(leaks.detector()).__name__ == "FakeDetector"
    assert "2 leak detectors installed; using alpha" in caplog.text


async def test_the_public_build_checks_nothing_and_knows_nothing(
    cache: Redis, hls_reader: HlsReader
) -> None:
    background = BackgroundTasks()
    stream = Stream(id=uuid.uuid4(), hls_path="rec")
    tv = ListenerTv(np.zeros((300, 16), dtype=np.float32), 0.0)
    await NoLeakDetector().schedule(background, hls_reader, cache, stream, tv)
    assert background.tasks == []
    assert await NoLeakDetector().verdict(cache, stream.id) == GameAudio.UNKNOWN
