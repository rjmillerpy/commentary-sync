"""Give every request an ID that appears on its log lines and in its response,
and write one access line per request."""

import logging
import re
import time
import uuid
from http import HTTPStatus

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
NO_REQUEST_ID = "-"  # outside a request, for example during startup
# The context keys every log line inside a request carries (app.common.logs).
REQUEST_ID_KEY = "request_id"
ACCOUNT_ID_KEY = "account_id"

# A caller may supply its own ID so one trace spans several services. It ends
# up in logs and a response header, so anything unusual is replaced.
ACCEPTED_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{8,64}")

# Probed every few seconds by Docker and the load balancer: debug, not info.
QUIET_PATHS = frozenset({"/health", "/health/live"})
MILLISECONDS_PER_SECOND = 1000

access_logger = logging.getLogger("app.access")


def current_request_id() -> str:
    request_id: str = structlog.contextvars.get_contextvars().get(REQUEST_ID_KEY, NO_REQUEST_ID)
    return request_id


def bind_account(account_id: uuid.UUID) -> None:
    """Name the signed-in account on the rest of this request's log lines (rule 41).
    The ID only: never the email."""
    structlog.contextvars.bind_contextvars(**{ACCOUNT_ID_KEY: str(account_id)})


class RequestIdMiddleware:
    """Accept or create the request ID, expose it to the app and the logs, echo
    it in the response, and log the request when it finishes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _accepted_or_new(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})[REQUEST_ID_KEY] = request_id
        # Stays 500 if the app raises before it starts a response.
        status = HTTPStatus.INTERNAL_SERVER_ERROR.value

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        started = time.perf_counter()
        # Both keys are reset when the request ends, so nothing carries over to
        # the next request handled in this context.
        context = {REQUEST_ID_KEY: request_id, ACCOUNT_ID_KEY: None}
        with structlog.contextvars.bound_contextvars(**context):
            try:
                await self.app(scope, receive, send_with_request_id)
            finally:
                _log_access(scope, status, time.perf_counter() - started)


def _log_access(scope: Scope, status: int, elapsed_seconds: float) -> None:
    """One line per request. The path without its query string, and no client
    IP address: neither is needed to trace a request, and both can be personal."""
    path: str = scope["path"]
    method: str = scope["method"]
    level = logging.DEBUG if path in QUIET_PATHS else logging.INFO
    access_logger.log(
        level,
        "%s %s %d",
        method,
        path,
        status,
        extra={
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(elapsed_seconds * MILLISECONDS_PER_SECOND, 1),
        },
    )


def _accepted_or_new(supplied: str | None) -> str:
    if supplied is not None and ACCEPTED_REQUEST_ID.fullmatch(supplied):
        return supplied
    return uuid.uuid4().hex
