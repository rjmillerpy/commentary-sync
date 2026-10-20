from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request, WebSocket
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.types import Message, Receive, Scope, Send

from app.common.body_limit import BodySizeLimitMiddleware

CAP = 100


@pytest.fixture
def capped() -> TestClient:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=CAP)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    @app.post("/json")
    async def json_body(payload: dict[str, str]) -> dict[str, int]:
        return {"keys": len(payload)}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        await socket.close()

    return TestClient(app)


def chunks(total: int, size: int = 30) -> Iterator[bytes]:
    """A body sent without a Content-Length (chunked)."""
    for start in range(0, total, size):
        yield b"x" * min(size, total - start)


@pytest.mark.parametrize(
    ("size", "status"), [(CAP, 200), (CAP + 1, 413)], ids=["at-the-cap", "one-over"]
)
def test_a_declared_length_over_the_cap_is_refused(
    capped: TestClient, size: int, status: int
) -> None:
    response = capped.post("/echo", content=b"x" * size)
    assert response.status_code == status
    if status == 413:
        assert response.json() == {"detail": "Request body too large"}


@pytest.mark.parametrize(("size", "status"), [(CAP, 200), (CAP * 3, 413)], ids=["under", "over"])
def test_a_chunked_body_is_counted_and_cut_off(capped: TestClient, size: int, status: int) -> None:
    response = capped.post("/echo", content=chunks(size))
    assert response.status_code == status


def test_json_endpoints_are_capped_too(capped: TestClient) -> None:
    oversized = '{"a": "' + "x" * CAP + '"}'
    assert (
        capped.post(
            "/json", content=chunks(len(oversized)).__iter__() and oversized.encode()
        ).status_code
        == 413
    )
    assert capped.post("/json", json={"a": "b"}).json() == {"keys": 1}


def test_websockets_pass_through(capped: TestClient) -> None:
    with capped.websocket_connect("/ws"):
        pass


# Driven directly at the ASGI level: a client that really goes away, and an
# app that has already answered before the body passes the cap.


class Wire:
    """A client and a server socket, as ASGI sees them."""

    def __init__(self, messages: list[Message]) -> None:
        self.incoming = list(messages)
        self.sent: list[Message] = []

    async def receive(self) -> Message:
        return self.incoming.pop(0)

    async def send(self, message: Message) -> None:
        self.sent.append(message)


SCOPE: Scope = {"type": "http", "method": "POST", "path": "/", "headers": []}


@pytest.mark.anyio
async def test_a_real_disconnect_is_not_mistaken_for_an_oversized_body() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        raise ClientDisconnect

    wire = Wire([{"type": "http.disconnect"}])
    with pytest.raises(ClientDisconnect):
        await BodySizeLimitMiddleware(app, max_bytes=CAP)(SCOPE, wire.receive, wire.send)
    assert wire.sent == []


@pytest.mark.anyio
async def test_an_app_that_answered_first_is_cut_off_without_a_second_answer() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await receive()
        await receive()  # the second chunk passes the cap
        await send({"type": "http.response.body", "body": b"late"})

    chunk = {"type": "http.request", "body": b"x" * CAP, "more_body": True}
    wire = Wire([chunk, chunk])
    await BodySizeLimitMiddleware(app, max_bytes=CAP)(SCOPE, wire.receive, wire.send)
    assert [message["type"] for message in wire.sent] == ["http.response.start"]
