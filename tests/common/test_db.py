import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import Settings
from app.common.db import create_database_engine, create_migration_engine

# Nothing listens on port 1, so the real Postgres driver is refused at once.
CLOSED_PORT_DATABASE_URL = "postgresql+psycopg://commentary:secret@127.0.0.1:1/commentary"
CONNECT_TIMEOUT_SECONDS = 2.0
FAIL_FAST_SECONDS = 10.0


@pytest.mark.anyio
async def test_engine_round_trips_a_real_row(settings: Settings) -> None:
    engine = create_database_engine(settings)
    async with AsyncSession(engine) as session:
        await session.execute(text("CREATE TABLE listener (name TEXT)"))
        await session.execute(text("INSERT INTO listener VALUES ('ada')"))
        await session.commit()
    async with AsyncSession(engine) as session:
        assert (await session.execute(text("SELECT name FROM listener"))).scalar_one() == "ada"
    await engine.dispose()


@pytest.mark.anyio
async def test_unreachable_postgres_fails_within_the_timeout(settings: Settings) -> None:
    """Rule 67: a database that is down must fail the call, not hang it."""
    postgres = settings.model_copy(
        update={
            "database_url": SecretStr(CLOSED_PORT_DATABASE_URL),
            "database_connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
        }
    )
    engine = create_database_engine(postgres)
    started = time.monotonic()
    with pytest.raises(OperationalError):
        async with AsyncSession(engine) as session:
            await session.execute(text("SELECT 1"))
    assert time.monotonic() - started < FAIL_FAST_SECONDS
    await engine.dispose()


@pytest.mark.anyio
async def test_creating_the_engine_does_not_connect(settings: Settings) -> None:
    """Startup must not depend on the database being up; /health reports it instead."""
    postgres = settings.model_copy(update={"database_url": SecretStr(CLOSED_PORT_DATABASE_URL)})
    await create_database_engine(postgres).dispose()


def test_requests_get_a_session_on_the_shared_pool(app: FastAPI, client: TestClient) -> None:
    assert client.get("/health").json()["checks"]["database"] == "ok"
    assert app.state.engine.pool.checkedout() == 0  # the session was closed after the response


@pytest.mark.anyio
async def test_migration_engine_also_fails_fast_when_postgres_is_down(settings: Settings) -> None:
    """Migrations have no statement timeout, but must not wait forever to connect."""
    postgres = settings.model_copy(
        update={
            "database_url": SecretStr(CLOSED_PORT_DATABASE_URL),
            "database_connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
        }
    )
    engine = create_migration_engine(postgres)
    started = time.monotonic()
    with pytest.raises(OperationalError):
        async with engine.connect():
            pass
    assert time.monotonic() - started < FAIL_FAST_SECONDS
    await engine.dispose()
