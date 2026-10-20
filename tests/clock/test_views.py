import time

from fastapi.testclient import TestClient


def test_the_clock_is_public_current_and_never_cached(client: TestClient) -> None:
    before = time.time()
    response = client.get("/clock")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert before <= response.json()["now"] <= time.time()
