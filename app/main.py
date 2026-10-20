"""FastAPI app factory: shared clients, request tracing, error boundary, routers.

uvicorn app.main:create_app --factory
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.views import auth_router
from app.clock.views import clock_router
from app.commentators.views import commentators_router
from app.common.body_limit import BodySizeLimitMiddleware
from app.common.cache import create_cache
from app.common.config import Settings
from app.common.db import create_database_engine
from app.common.logs import configure_logging
from app.common.rate_limit import RateLimit, rate_limited
from app.common.request_tracing import NO_REQUEST_ID, REQUEST_ID_HEADER, RequestIdMiddleware
from app.common.schema import ErrorResponse, ValidationErrorResponse, ValidationIssue
from app.common.security_headers import SecurityHeadersMiddleware
from app.events.views import events_router
from app.health.views import health_router
from app.streams.recorder import create_recorder
from app.streams.views import streams_router
from app.streams.webhooks import webhooks_router

logger = logging.getLogger(__name__)

APP_TITLE = "commentary-sync"
# Browsers send credentials as a bearer token, never a cookie, so CORS
# credentials stay off.
CORS_METHODS = ("GET", "POST", "PATCH")
CORS_HEADERS = ("Authorization", "Content-Type")
CORS_MAX_AGE_SECONDS = 10 * 60
INTERNAL_ERROR_DETAIL = "Internal server error"
DOCS_URL = "/docs"
REDOC_URL = "/redoc"
OPENAPI_URL = "/openapi.json"

# Every client's requests to the public routes, together: far above what the
# studio or the app sends (a listener makes about 4 a minute), low enough to
# stop one address scraping or hammering the API. Endpoints with costlier
# work have tighter limits of their own.
ALL_REQUESTS_PER_MINUTE = RateLimit("all-minute", limit=300, window_seconds=60)

# One row per domain: adding a domain is a one-line change. The last column
# says whether ALL_REQUESTS_PER_MINUTE applies: not to health checks (the load
# balancer's) or LiveKit's webhooks (one sender, in bursts).
ROUTERS: tuple[tuple[APIRouter, str, bool], ...] = (
    (health_router, "/health", False),
    (clock_router, "/clock", True),
    (auth_router, "/auth", True),
    (events_router, "/events", True),
    (commentators_router, "/commentators", True),
    (streams_router, "/streams", True),
    (webhooks_router, "/webhooks", False),
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Settings come from the environment unless given."""
    # pydantic-settings fills the required fields from the environment, which mypy can't see.
    resolved = settings if settings is not None else Settings()  # type: ignore[call-arg]
    configure_logging(resolved.log_level, resolved.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One pool, one Redis client and one LiveKit API client for the whole
        # app, closed on shutdown (uvicorn runs this on SIGTERM, after
        # in-flight requests finish).
        app.state.engine = create_database_engine(resolved)
        app.state.cache = create_cache(resolved)
        app.state.recorder = create_recorder(resolved)
        try:
            yield
        finally:
            if app.state.recorder is not None:
                await app.state.recorder.aclose()
            await app.state.cache.aclose()
            await app.state.engine.dispose()
            logger.info("database pool and cache client closed")

    app = FastAPI(
        title=APP_TITLE,
        lifespan=lifespan,
        # A deployed API serves no docs pages and no schema (COMMENTARY_API_DOCS=false).
        docs_url=DOCS_URL if resolved.api_docs else None,
        redoc_url=REDOC_URL if resolved.api_docs else None,
        openapi_url=OPENAPI_URL if resolved.api_docs else None,
    )
    app.state.settings = resolved
    _add_middleware(app, resolved)
    app.exception_handler(RequestValidationError)(handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
    for router, prefix, is_limited in ROUTERS:
        limits = [Depends(rate_limited(ALL_REQUESTS_PER_MINUTE))] if is_limited else []
        app.include_router(router, prefix=prefix, dependencies=limits)
    return app


def _add_middleware(app: FastAPI, settings: Settings) -> None:
    """The last one added runs first on the way in."""
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(SecurityHeadersMiddleware, hsts_seconds=settings.hsts_seconds)
    app.add_middleware(RequestIdMiddleware)
    if settings.cors_origins:
        # Added last, so it runs first: a preflight is answered before anything else.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=list(CORS_METHODS),
            allow_headers=list(CORS_HEADERS),
            expose_headers=[REQUEST_ID_HEADER],
            max_age=CORS_MAX_AGE_SECONDS,
        )


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """The last error boundary: log the cause, tell the client only that it failed.

    The request ID is in both, so a user's report can be matched to the log.
    """
    request_id: str = getattr(request.state, "request_id", NO_REQUEST_ID)
    logger.error(
        "unhandled error on %s %s",
        request.method,
        request.url.path,
        exc_info=error,
        extra={"request_id": request_id},
    )
    body = ErrorResponse(detail=INTERNAL_ERROR_DETAIL, request_id=request_id)
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=body.model_dump(),
        headers={REQUEST_ID_HEADER: request_id},
    )


async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    """422 with what was wrong and where, never the rejected value itself."""
    # Built field by field, so FastAPI's `input` (the value sent), `ctx` and
    # `url` are left out.
    body = ValidationErrorResponse(
        detail=tuple(
            ValidationIssue(type=issue["type"], loc=issue["loc"], msg=issue["msg"])
            for issue in error.errors()
        )
    )
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY, content=body.model_dump(mode="json")
    )
