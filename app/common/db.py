"""The database boundary: one shared connection pool, one session per request."""

import math
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import URL, NullPool, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.common.config import Settings

POSTGRES_BACKEND = "postgresql"
MILLISECONDS_PER_SECOND = 1000


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Build the app's one connection pool. Nothing connects until first use."""
    url = make_url(settings.database_url.get_secret_value())
    return create_async_engine(
        url,
        pool_pre_ping=True,  # replace connections the server closed while idle
        pool_timeout=settings.database_connect_timeout_seconds,
        connect_args=_connect_arguments(
            url,
            settings.database_connect_timeout_seconds,
            settings.database_statement_timeout_seconds,
        ),
    )


def create_migration_engine(settings: Settings) -> AsyncEngine:
    """An engine for one migration run: a single connection, never pooled.

    It has the connect timeout but no statement timeout, because building an
    index on a large table legitimately takes longer than any request may.
    """
    url = make_url(settings.database_url.get_secret_value())
    return create_async_engine(
        url,
        poolclass=NullPool,
        connect_args=_connect_arguments(url, settings.database_connect_timeout_seconds, None),
    )


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a session on the shared pool, closed after the response."""
    engine: AsyncEngine = request.app.state.engine
    # expire_on_commit=False: reading an expired attribute would be a hidden
    # database call, which async code can't make outside an await.
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


def _connect_arguments(
    url: URL, connect_timeout_seconds: float, statement_timeout_seconds: float | None
) -> dict[str, object]:
    """Timeouts for connecting and, when given, for each statement.

    Only Postgres takes them. The tests' SQLite is a local file, with no
    network to wait on.
    """
    if url.get_backend_name() != POSTGRES_BACKEND:
        return {}
    arguments: dict[str, object] = {"connect_timeout": math.ceil(connect_timeout_seconds)}
    if statement_timeout_seconds is not None:
        statement_timeout_ms = int(statement_timeout_seconds * MILLISECONDS_PER_SECOND)
        arguments["options"] = f"-c statement_timeout={statement_timeout_ms}"
    return arguments
