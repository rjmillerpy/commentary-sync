import uuid
from collections.abc import Callable

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import Settings
from app.events import espn, service
from app.events.schema import League
from app.main import create_app
from tests.events.conftest import NBA_DAY, NFL_DAY

pytestmark = pytest.mark.anyio

SINCE_ALL = "2000-01-01T00:00:00Z"


@pytest.fixture
async def seeded_client(
    migrated_settings: Settings,
    db: AsyncSession,
    http_client_factory: Callable[[float], httpx2.AsyncClient],
    app: FastAPI,
) -> TestClient:
    async with http_client_factory(1.0) as http:
        source = espn.EspnSchedule(http, retry_delay_seconds=0)
        await service.import_schedule(db, source, League.NFL, NFL_DAY, 1)
        await service.import_schedule(db, source, League.NBA, NBA_DAY, 1)
    return TestClient(app)


async def test_lists_events_with_their_networks(seeded_client: TestClient) -> None:
    with seeded_client as client:
        response = client.get("/events", params={"starts_after": SINCE_ALL})
    assert response.status_code == 200
    page = response.json()
    assert len(page["items"]) == 14
    assert page["next_offset"] is None
    first = page["items"][0]
    assert set(first) == {
        "id",
        "league",
        "title",
        "home_team",
        "away_team",
        "starts_at",
        "status",
        "networks",
    }
    assert first["title"] == "Houston Texans at Jacksonville Jaguars"
    assert first["networks"] == ["NFL Net"]
    assert first["status"] == "scheduled"


async def test_filters_by_league(seeded_client: TestClient) -> None:
    with seeded_client as client:
        page = client.get("/events", params={"league": "nba", "starts_after": SINCE_ALL}).json()
    assert {item["league"] for item in page["items"]} == {"nba"}
    assert len(page["items"]) == 2


async def test_pages_report_where_the_next_one_starts(seeded_client: TestClient) -> None:
    with seeded_client as client:
        first = client.get("/events", params={"limit": 10, "starts_after": SINCE_ALL}).json()
        second = client.get(
            "/events",
            params={"limit": 10, "offset": first["next_offset"], "starts_after": SINCE_ALL},
        ).json()
    assert (first["next_offset"], len(first["items"])) == (10, 10)
    assert (second["next_offset"], len(second["items"])) == (None, 4)


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 10_001},
        {"league": "mlb"},
        {"starts_after": "yesterday"},
    ],
    ids=[
        "limit-zero",
        "limit-over-100",
        "offset-negative",
        "offset-too-deep",
        "unknown-league",
        "bad-date",
    ],
)
async def test_rejects_bad_query_parameters(
    client: TestClient, params: dict[str, str | int]
) -> None:
    """Rule 5 and 11: input is validated at the boundary and pages are bounded."""
    assert client.get("/events", params=params).status_code == 422


async def test_gets_one_event(seeded_client: TestClient) -> None:
    with seeded_client as client:
        listed = client.get("/events", params={"league": "nba", "starts_after": SINCE_ALL}).json()
        event_id = listed["items"][0]["id"]
        response = client.get(f"/events/{event_id}")
    assert response.status_code == 200
    assert response.json() == listed["items"][0]


async def test_missing_event_is_404(migrated_settings: Settings, client: TestClient) -> None:
    response = client.get(f"/events/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


async def test_malformed_event_id_is_422(client: TestClient) -> None:
    assert client.get("/events/not-a-uuid").status_code == 422


@pytest.mark.parametrize(
    ("path", "status", "model"),
    [
        ("/events", "200", "EventPage"),
        ("/events/{event_id}", "200", "EventResponse"),
        ("/events/{event_id}", "404", "ErrorDetail"),
    ],
    ids=["list-200", "get-200", "get-404"],
)
def test_documented_with_a_response_schema(
    settings: Settings, path: str, status: str, model: str
) -> None:
    """Rule 46: the OpenAPI schema names a model, not a free-form object."""
    schema = TestClient(create_app(settings)).get("/openapi.json").json()
    documented = schema["paths"][path]["get"]["responses"][status]
    assert documented["content"]["application/json"]["schema"]["$ref"].endswith(f"/{model}")
