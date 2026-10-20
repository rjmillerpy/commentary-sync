import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from app.common.security_headers import API_CSP, SecurityHeadersMiddleware


def client(hsts_seconds: int = 0) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts_seconds=hsts_seconds)

    @app.get("/thing")
    def thing() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/framed")
    def framed() -> dict[str, str]:
        return {}

    return TestClient(app)


def test_every_response_says_it_is_not_a_page() -> None:
    headers = client().get("/thing").headers
    assert headers["Content-Security-Policy"] == API_CSP
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_errors_carry_them_too() -> None:
    assert client().get("/missing").headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("path", ["/docs", "/redoc"], ids=["swagger", "redoc"])
def test_the_docs_pages_can_load_their_scripts(path: str) -> None:
    response = client().get(path)
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.parametrize(
    ("hsts_seconds", "expected"),
    [(0, None), (31_536_000, "max-age=31536000; includeSubDomains")],
    ids=["plain-http", "behind-https"],
)
def test_hsts_only_when_served_over_https(hsts_seconds: int, expected: str | None) -> None:
    assert client(hsts_seconds).get("/thing").headers.get("Strict-Transport-Security") == expected


def test_websockets_pass_through_untouched() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        await socket.send_text("hi")
        await socket.close()

    with TestClient(app).websocket_connect("/ws") as socket:
        assert socket.receive_text() == "hi"
