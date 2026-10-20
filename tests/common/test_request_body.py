import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.common.request_body import read_limited_body

LIMIT = 10


@pytest.fixture
def echo() -> TestClient:
    app = FastAPI()

    @app.post("/echo")
    async def echo_body(request: Request) -> dict[str, int]:
        return {"bytes": len(await read_limited_body(request, LIMIT))}

    return TestClient(app)


@pytest.mark.parametrize(
    ("size", "status"),
    [(0, 200), (LIMIT, 200), (LIMIT + 1, 413)],
    ids=["empty", "at-the-limit", "one-over"],
)
def test_bodies_over_the_limit_are_refused(echo: TestClient, size: int, status: int) -> None:
    response = echo.post("/echo", content=b"x" * size)
    assert response.status_code == status
    if status == 200:
        assert response.json() == {"bytes": size}
    else:
        assert response.json() == {"detail": "Request body too large"}
