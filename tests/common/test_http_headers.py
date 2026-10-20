import pytest
from fastapi.testclient import TestClient

from app.common.http_headers import CACHE_CONTROL_HEADER, NO_STORE, RETRY_AFTER_HEADER


@pytest.mark.parametrize(
    ("name", "expected"),
    [(CACHE_CONTROL_HEADER, "Cache-Control"), (RETRY_AFTER_HEADER, "Retry-After")],
    ids=["cache-control", "retry-after"],
)
def test_header_names_are_the_standard_ones(name: str, expected: str) -> None:
    assert name == expected


def test_live_responses_are_not_cached(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.headers[CACHE_CONTROL_HEADER] == NO_STORE
