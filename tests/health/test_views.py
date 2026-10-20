import pytest
from fastapi.testclient import TestClient

PATHS = ["/health", "/health/live"]
PATH_IDS = ["ready", "live"]


def test_live_is_ok(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_live_stays_ok_during_an_outage(client_with_outage: TestClient) -> None:
    """Liveness must not depend on the database or Redis (see service.liveness)."""
    assert client_with_outage.get("/health/live").status_code == 200


def test_ready_is_ok_when_dependencies_answer(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}


def test_ready_is_503_during_an_outage(client_with_outage: TestClient) -> None:
    response = client_with_outage.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "cache": "unavailable"},
    }


def test_failure_detail_is_not_returned(client_with_outage: TestClient) -> None:
    """Unauthenticated endpoint: no driver message, address, path or SQL in the body."""
    body = client_with_outage.get("/health").text.lower()
    for leaked in ("unable to open", "sqlite", "select", "127.0.0.1", "refused"):
        assert leaked not in body


@pytest.mark.parametrize("path", PATHS, ids=PATH_IDS)
def test_no_auth_required(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", PATHS, ids=PATH_IDS)
def test_never_cached(client: TestClient, path: str) -> None:
    assert client.get(path).headers["cache-control"] == "no-store"


def test_503_is_never_cached_either(client_with_outage: TestClient) -> None:
    assert client_with_outage.get("/health").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("path", "status", "model"),
    [
        ("/health", "200", "ReadinessResponse"),
        ("/health", "503", "ReadinessResponse"),
        ("/health/live", "200", "LivenessResponse"),
    ],
    ids=["ready-200", "ready-503", "live-200"],
)
def test_documented_with_a_response_schema(
    client: TestClient, path: str, status: str, model: str
) -> None:
    """Rule 46: the OpenAPI schema names a model, not a free-form object."""
    documented = client.get("/openapi.json").json()["paths"][path]["get"]["responses"][status]
    reference = documented["content"]["application/json"]["schema"]["$ref"]
    assert reference.endswith(f"/{model}")
