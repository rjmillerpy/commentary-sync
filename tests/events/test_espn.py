import json
from datetime import UTC, datetime

import httpx2
import pytest

from app.events import espn
from app.events.errors import EventSourceError
from app.events.schema import EventStatus, League
from tests.events.conftest import NBA_DAY, NFL_DAY, FakeEspn, event_with_status, recording

pytestmark = pytest.mark.anyio


async def test_reads_a_real_nfl_sunday(schedule: espn.EspnSchedule) -> None:
    events = await schedule.fetch_day(League.NFL, NFL_DAY)
    assert len(events) == 12
    first = events[0]
    assert first.source == "espn"
    assert first.source_event_id == "401872996"
    assert first.league is League.NFL
    assert first.title == "Houston Texans at Jacksonville Jaguars"
    assert first.home_team == "Jacksonville Jaguars"
    assert first.away_team == "Houston Texans"
    assert first.starts_at == datetime(2026, 10, 18, 13, 30, tzinfo=UTC)
    assert first.status is EventStatus.SCHEDULED
    assert first.networks == ("NFL Net",)
    assert {event.networks for event in events} >= {("CBS",), ("Fox",), ("NBC",)}


async def test_reads_a_real_nba_night(schedule: espn.EspnSchedule) -> None:
    events = await schedule.fetch_day(League.NBA, NBA_DAY)
    assert [event.title for event in events] == [
        "Cleveland Cavaliers at Philadelphia 76ers",
        "Denver Nuggets at Oklahoma City Thunder",
    ]
    assert all(event.networks == ("ESPN",) for event in events)


@pytest.mark.parametrize(
    ("league", "path"),
    [(League.NFL, "/football/nfl/scoreboard"), (League.NBA, "/basketball/nba/scoreboard")],
    ids=["nfl", "nba"],
)
async def test_asks_for_the_right_league_and_day(
    schedule: espn.EspnSchedule, fake_espn: FakeEspn, league: League, path: str
) -> None:
    await schedule.fetch_day(league, NFL_DAY)
    request = fake_espn.requests[0]
    assert request.url.path == f"/apis/site/v2/sports{path}"
    assert request.url.params["dates"] == "20261018"


async def test_a_day_without_games_is_empty(schedule: espn.EspnSchedule) -> None:
    assert await schedule.fetch_day(League.NFL, NBA_DAY) == []


@pytest.mark.parametrize(
    ("name", "state", "expected"),
    [
        ("STATUS_SCHEDULED", "pre", EventStatus.SCHEDULED),
        ("STATUS_IN_PROGRESS", "in", EventStatus.LIVE),
        ("STATUS_HALFTIME", "in", EventStatus.LIVE),
        ("STATUS_FINAL", "post", EventStatus.FINAL),
        ("STATUS_POSTPONED", "post", EventStatus.POSTPONED),
        ("STATUS_CANCELED", "post", EventStatus.CANCELLED),
    ],
    ids=["scheduled", "in-progress", "halftime", "final", "postponed", "cancelled"],
)
async def test_maps_espn_statuses(
    schedule: espn.EspnSchedule,
    fake_espn: FakeEspn,
    name: str,
    state: str,
    expected: EventStatus,
) -> None:
    fake_espn.override = lambda _: httpx2.Response(200, content=event_with_status(name, state))
    [event] = await schedule.fetch_day(League.NFL, NFL_DAY)
    assert event.status is expected


async def test_unknown_status_is_refused(schedule: espn.EspnSchedule, fake_espn: FakeEspn) -> None:
    fake_espn.override = lambda _: httpx2.Response(
        200, content=event_with_status("STATUS_SOMETHING_NEW", "weird")
    )
    with pytest.raises(EventSourceError, match="unknown"):
        await schedule.fetch_day(League.NFL, NFL_DAY)


@pytest.mark.parametrize(
    "body",
    [b"not json", b'{"no_events": []}', b'{"events": [{"id": "1"}]}'],
    ids=["not-json", "no-events-key", "event-missing-fields"],
)
async def test_unusable_payload_is_a_source_error(
    schedule: espn.EspnSchedule, fake_espn: FakeEspn, body: bytes
) -> None:
    """Rule 5: third-party data is validated at the boundary."""
    fake_espn.override = lambda _: httpx2.Response(200, content=body)
    with pytest.raises(EventSourceError, match="unexpected"):
        await schedule.fetch_day(League.NFL, NFL_DAY)


async def test_event_without_a_home_team_is_refused(
    schedule: espn.EspnSchedule, fake_espn: FakeEspn
) -> None:
    payload = recording("espn_nfl_2026-10-18.json")
    events = payload["events"]
    assert isinstance(events, list)
    for competitor in events[0]["competitions"][0]["competitors"]:
        competitor["homeAway"] = "away"
    body = json.dumps({"events": [events[0]]}).encode()
    fake_espn.override = lambda _: httpx2.Response(200, content=body)
    with pytest.raises(EventSourceError, match="home and away"):
        await schedule.fetch_day(League.NFL, NFL_DAY)


@pytest.mark.parametrize("status", [429, 500, 503], ids=["rate-limited", "500", "503"])
async def test_retries_transient_errors_then_succeeds(
    schedule: espn.EspnSchedule, fake_espn: FakeEspn, status: int
) -> None:
    responses = iter([httpx2.Response(status), httpx2.Response(200, content=b'{"events": []}')])
    fake_espn.override = lambda _: next(responses)
    assert await schedule.fetch_day(League.NFL, NFL_DAY) == []
    assert len(fake_espn.requests) == 2


async def test_retries_timeouts(schedule: espn.EspnSchedule, fake_espn: FakeEspn) -> None:
    def time_out_once(request: httpx2.Request) -> httpx2.Response:
        if len(fake_espn.requests) == 1:
            raise httpx2.ReadTimeout("slow", request=request)
        return httpx2.Response(200, content=b'{"events": []}')

    fake_espn.override = time_out_once
    assert await schedule.fetch_day(League.NFL, NFL_DAY) == []
    assert len(fake_espn.requests) == 2


async def test_gives_up_after_the_last_attempt(
    schedule: espn.EspnSchedule, fake_espn: FakeEspn, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule 31: retries are bounded."""
    fake_espn.override = lambda _: httpx2.Response(503)
    with pytest.raises(EventSourceError, match="after 3 attempts"):
        await schedule.fetch_day(League.NFL, NFL_DAY)
    assert len(fake_espn.requests) == espn.MAX_ATTEMPTS
    assert caplog.text.count("HTTP 503") == espn.MAX_ATTEMPTS


@pytest.mark.parametrize("status", [400, 403, 404], ids=["400", "403", "404"])
async def test_client_errors_are_not_retried(
    schedule: espn.EspnSchedule, fake_espn: FakeEspn, status: int
) -> None:
    fake_espn.override = lambda _: httpx2.Response(status)
    with pytest.raises(EventSourceError, match=str(status)):
        await schedule.fetch_day(League.NFL, NFL_DAY)
    assert len(fake_espn.requests) == 1


async def test_waits_longer_after_each_failure(fake_espn: FakeEspn) -> None:
    """Exponential backoff, measured with a real (tiny) delay."""
    fake_espn.override = lambda _: httpx2.Response(503)
    transport = httpx2.MockTransport(fake_espn.handle)
    async with httpx2.AsyncClient(base_url=espn.BASE_URL, transport=transport) as http:
        source = espn.EspnSchedule(http, retry_delay_seconds=0.05)
        started = datetime.now(UTC)
        with pytest.raises(EventSourceError):
            await source.fetch_day(League.NFL, NFL_DAY)
    assert (datetime.now(UTC) - started).total_seconds() >= 0.15  # 0.05 + 0.10


async def test_real_client_sends_a_user_agent_and_has_a_timeout() -> None:
    async with espn.create_http_client(4.0) as http:
        assert http.headers["User-Agent"] == espn.USER_AGENT
        assert http.timeout.read == 4.0
        assert str(http.base_url).startswith(espn.BASE_URL)
