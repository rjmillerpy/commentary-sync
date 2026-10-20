import logging
from collections.abc import Iterator

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from redis.asyncio import Redis

from app.common.cache import get_cache
from app.common.config import Settings
from app.common.request_tracing import REQUEST_ID_HEADER
from app.common.schema import ValidationErrorResponse
from app.main import ALL_REQUESTS_PER_MINUTE, create_app
from app.streams.recorder import Recorder
from tests.conftest import REQUIRED_ENVIRONMENT

SENSITIVE_CAUSE = "db-internal-7 at 10.0.0.5 refused user admin"


@pytest.fixture
def client_with_failing_route(app: FastAPI, client: TestClient) -> TestClient:
    @app.get("/fail")
    def fail() -> None:
        raise RuntimeError(SENSITIVE_CAUSE)

    return client


def test_unexpected_error_becomes_a_plain_500(client_with_failing_route: TestClient) -> None:
    response = client_with_failing_route.get("/fail")
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": response.headers[REQUEST_ID_HEADER],
    }


def test_unexpected_error_does_not_leak_its_cause(client_with_failing_route: TestClient) -> None:
    """Rule 10: no exception message, type or stack trace reaches the client."""
    body = client_with_failing_route.get("/fail").text
    for leaked in (SENSITIVE_CAUSE, "RuntimeError", "Traceback"):
        assert leaked not in body


def test_unexpected_error_is_logged_with_the_request_id(
    client_with_failing_route: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule 41: the ID a user reports finds the log line with the cause."""
    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = client_with_failing_route.get("/fail", headers={REQUEST_ID_HEADER: "trace-0001"})
    record = next(item for item in caplog.records if item.name == "app.main")
    assert response.json()["request_id"] == "trace-0001"
    assert record.__dict__["request_id"] == "trace-0001"
    assert record.getMessage() == "unhandled error on GET /fail"
    assert SENSITIVE_CAUSE in caplog.text


def test_health_routes_are_registered(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/health/live", "/auth/login", "/events"} <= set(paths)


def test_settings_default_to_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    monkeypatch.setenv("COMMENTARY_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/env.db")
    monkeypatch.setenv("COMMENTARY_CACHE_URL", "redis://127.0.0.1:1/0")
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    with TestClient(create_app()) as client:
        assert client.get("/health/live").status_code == 200


def test_shutdown_closes_the_shared_clients(app: FastAPI, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.main"), TestClient(app):
        pass
    assert "database pool and cache client closed" in caplog.text


def test_with_hls_on_the_app_opens_and_closes_a_recorder(settings: Settings, cache: Redis) -> None:
    hls = settings.model_copy(
        update={
            "livekit_api_url": HttpUrl("http://livekit.test:7880"),
            "hls_base_url": HttpUrl("https://hls.example.com"),
        }
    )
    app = create_app(hls)
    app.dependency_overrides[get_cache] = lambda: cache
    with TestClient(app):
        recorder = app.state.recorder
        assert isinstance(recorder, Recorder)
        assert not recorder.client.is_closed
    assert recorder.client.is_closed


def test_validation_errors_say_what_and_where_but_not_the_value(client: TestClient) -> None:
    """Rule 10: FastAPI would echo the rejected input, which can be a password."""
    response = client.get("/events", params={"limit": "rejected-value-7"})
    assert response.status_code == 422
    body = ValidationErrorResponse.model_validate(response.json())
    [issue] = body.detail
    assert set(response.json()["detail"][0]) == {"type", "loc", "msg"}
    assert issue.loc == ("query", "limit")
    assert issue.type == "int_parsing"
    assert "rejected-value-7" not in response.text


STUDIO_ORIGIN = "http://localhost:3000"


@pytest.fixture
def cors_client(settings: Settings) -> Iterator[TestClient]:
    allowed = settings.model_copy(update={"cors_origins": (STUDIO_ORIGIN,)})
    with TestClient(create_app(allowed)) as client:
        yield client


def preflight(client: TestClient, origin: str) -> httpx2.Response:
    return client.options(
        "/health/live",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_an_allowed_origin_may_call_the_api(cors_client: TestClient) -> None:
    response = preflight(cors_client, STUDIO_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == STUDIO_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_responses_to_an_allowed_origin_expose_the_request_id(cors_client: TestClient) -> None:
    response = cors_client.get("/health/live", headers={"Origin": STUDIO_ORIGIN})
    assert response.headers["access-control-allow-origin"] == STUDIO_ORIGIN
    assert response.headers["access-control-expose-headers"] == REQUEST_ID_HEADER


@pytest.mark.parametrize(
    "origin", ["http://evil.example", "http://localhost:3001"], ids=["other-site", "other-port"]
)
def test_other_origins_get_no_cors_headers(cors_client: TestClient, origin: str) -> None:
    """Security: only the configured studio origin can read responses in a browser."""
    response = preflight(cors_client, origin)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_without_configured_origins_no_browser_origin_is_allowed(client: TestClient) -> None:
    response = client.get("/health/live", headers={"Origin": STUDIO_ORIGIN})
    assert "access-control-allow-origin" not in response.headers


def test_a_deployed_api_serves_no_docs(settings: Settings, cache: Redis) -> None:
    app = create_app(settings.model_copy(update={"api_docs": False}))
    app.dependency_overrides[get_cache] = lambda: cache
    with TestClient(app) as deployed:
        assert [
            deployed.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")
        ] == [404] * 3


def test_responses_carry_the_security_headers(client: TestClient) -> None:
    headers = client.get("/health/live").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_oversized_bodies_are_refused_before_any_endpoint(client: TestClient) -> None:
    assert client.post("/auth/login", content=b"x" * (3 * 1024 * 1024)).status_code == 413


def test_all_public_routes_share_one_per_client_limit(client: TestClient) -> None:
    """Security: one address can't hammer or scrape the API; health checks are exempt."""
    statuses = [client.get("/clock").status_code for _ in range(ALL_REQUESTS_PER_MINUTE.limit + 1)]
    assert statuses[-1] == 429
    assert client.get("/events").status_code == 429  # the same budget
    assert client.get("/health/live").status_code == 200
