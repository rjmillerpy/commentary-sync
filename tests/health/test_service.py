import logging

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.common.config import Settings
from app.common.db import create_database_engine
from app.health import service
from app.health.schema import HealthStatus

OK = HealthStatus.OK
UNAVAILABLE = HealthStatus.UNAVAILABLE


@pytest.fixture
def engine(settings: Settings) -> AsyncEngine:
    return create_database_engine(settings)


def test_liveness_is_ok() -> None:
    assert service.liveness().status is OK


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("engine_fixture", "cache_fixture", "database", "cache_status", "overall"),
    [
        ("engine", "cache", OK, OK, OK),
        ("unreachable_engine", "cache", UNAVAILABLE, OK, UNAVAILABLE),
        ("engine", "unreachable_cache", OK, UNAVAILABLE, UNAVAILABLE),
        ("unreachable_engine", "unreachable_cache", UNAVAILABLE, UNAVAILABLE, UNAVAILABLE),
    ],
    ids=["both-up", "database-down", "cache-down", "both-down"],
)
async def test_readiness_reports_each_dependency(
    request: pytest.FixtureRequest,
    engine_fixture: str,
    cache_fixture: str,
    database: HealthStatus,
    cache_status: HealthStatus,
    overall: HealthStatus,
) -> None:
    database_engine: AsyncEngine = request.getfixturevalue(engine_fixture)
    redis_client: Redis = request.getfixturevalue(cache_fixture)
    async with AsyncSession(database_engine) as session:
        result = await service.readiness(session, redis_client)
    await database_engine.dispose()
    assert result.checks.database is database
    assert result.checks.cache is cache_status
    assert result.status is overall


@pytest.mark.anyio
async def test_failures_are_logged_with_their_cause(
    unreachable_engine: AsyncEngine, unreachable_cache: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.health.service"):
        async with AsyncSession(unreachable_engine) as session:
            await service.readiness(session, unreachable_cache)
    assert "database ping failed" in caplog.text
    assert "unable to open database file" in caplog.text
    assert "cache ping failed" in caplog.text
    assert "127.0.0.1:1" in caplog.text
