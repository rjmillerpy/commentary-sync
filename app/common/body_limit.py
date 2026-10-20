"""A cap on every request body, before any endpoint reads it.

Endpoints that take raw audio cap their own bodies tighter
(request_body.read_limited_body); this is the ceiling for everything else,
JSON included, so no request can make the API buffer an unlimited body. A
declared Content-Length over the cap is refused at once; a body sent without
one (chunked) is counted as it arrives and cut off at the cap.
"""

import json
from http import HTTPStatus

from starlette.datastructures import Headers
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOO_LARGE_BODY = json.dumps({"detail": "Request body too large"}).encode()


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await _refuse(send)
            return
        await _CountedRequest(self.app, self.max_bytes, receive, send).run(scope)


class _CountedRequest:
    """One request whose body is counted as the app reads it. Past the cap,
    the app is told the client went away, its own reply is dropped, and a
    413 goes out instead (if nothing has been sent yet)."""

    def __init__(self, app: ASGIApp, max_bytes: int, receive: Receive, send: Send) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.receive = receive
        self.send = send
        self.received = 0
        self.is_over = False
        self.has_started = False

    async def run(self, scope: Scope) -> None:
        try:
            await self.app(scope, self.counted_receive, self.guarded_send)
        except ClientDisconnect:
            # What reading a body cut off at the cap raises; a real disconnect
            # has no one to answer.
            if not self.is_over:
                raise
        if self.is_over and not self.has_started:
            await _refuse(self.send)

    async def counted_receive(self) -> Message:
        message = await self.receive()
        if message["type"] == "http.request":
            self.received += len(message.get("body", b""))
            if self.received > self.max_bytes:
                self.is_over = True
                return {"type": "http.disconnect"}
        return message

    async def guarded_send(self, message: Message) -> None:
        if self.is_over:
            return  # the 413 replaces whatever the app says
        if message["type"] == "http.response.start":
            self.has_started = True
        await self.send(message)


async def _refuse(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": HTTPStatus.REQUEST_ENTITY_TOO_LARGE.value,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(TOO_LARGE_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": TOO_LARGE_BODY})
