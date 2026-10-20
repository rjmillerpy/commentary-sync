"""Fixtures for the events tests: a migrated database and ESPN, replayed from recordings.

The recordings in fixtures/ are real ESPN responses (2026-10-18 NFL, 2026-10-22
NBA), trimmed to the fields the importer reads. The network is the only thing
replaced: requests go through the real client code into httpx2's MockTransport.
"""

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx2
import pytest

from app.events import espn

FIXTURES = Path(__file__).parent / "fixtures"
NFL_DAY = date(2026, 10, 18)
NBA_DAY = date(2026, 10, 22)
RECORDINGS = {
    ("football/nfl", "20261018"): "espn_nfl_2026-10-18.json",
    ("basketball/nba", "20261022"): "espn_nba_2026-10-22.json",
}
EMPTY_DAY = b'{"events": []}'

Handler = Callable[[httpx2.Request], httpx2.Response]


def recording(name: str) -> dict[str, object]:
    loaded: dict[str, object] = json.loads((FIXTURES / name).read_text())
    return loaded


def event_with_status(name: str, state: str) -> bytes:
    """The first recorded NFL event alone, with its status replaced."""
    payload = recording("espn_nfl_2026-10-18.json")
    events = payload["events"]
    assert isinstance(events, list)
    first = events[0]
    first["competitions"][0]["status"]["type"] = {"name": name, "state": state}
    return json.dumps({"events": [first]}).encode()


@dataclass
class FakeEspn:
    """ESPN's scoreboard, answering from the recordings; other days are empty."""

    requests: list[httpx2.Request] = field(default_factory=list)
    override: Handler | None = None

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.override is not None:
            return self.override(request)
        league_path = request.url.path.removeprefix("/apis/site/v2/sports/").removesuffix(
            "/scoreboard"
        )
        name = RECORDINGS.get((league_path, request.url.params["dates"]))
        body = (FIXTURES / name).read_bytes() if name else EMPTY_DAY
        return httpx2.Response(200, content=body)


@pytest.fixture
def fake_espn() -> FakeEspn:
    return FakeEspn()


@pytest.fixture
def http_client_factory(fake_espn: FakeEspn) -> Callable[[float], httpx2.AsyncClient]:
    """Like espn.create_http_client, but the requests reach FakeEspn."""

    def build(timeout_seconds: float) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            base_url=espn.BASE_URL,
            timeout=httpx2.Timeout(timeout_seconds),
            transport=httpx2.MockTransport(fake_espn.handle),
        )

    return build


@pytest.fixture
async def schedule(
    http_client_factory: Callable[[float], httpx2.AsyncClient],
) -> AsyncIterator[espn.EspnSchedule]:
    async with http_client_factory(1.0) as http:
        yield espn.EspnSchedule(http, retry_delay_seconds=0)
