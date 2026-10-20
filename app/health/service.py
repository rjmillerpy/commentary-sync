"""What "healthy" means: the checks behind the health endpoints."""

import asyncio
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.health.schema import HealthStatus, LivenessResponse, ReadinessChecks, ReadinessResponse

logger = logging.getLogger(__name__)

# The cheapest query that proves a round trip to the database works.
DATABASE_PING = text("SELECT 1")


def liveness() -> LivenessResponse:
    """The process is up. Deliberately checks nothing else: an orchestrator
    restarts a container that fails liveness, and a restart can't fix a
    database or Redis outage."""
    return LivenessResponse(status=HealthStatus.OK)


async def readiness(db: AsyncSession, cache: Redis) -> ReadinessResponse:
    """Can this instance do real work? The database and Redis must both answer.

    Each ping is bounded by the timeouts set where the clients are built
    (app.common.db, app.common.cache), and the two run at the same time. A
    failed ping is not retried: the caller's next probe is the retry.
    """
    database, cache_status = await asyncio.gather(_check_database(db), _check_cache(cache))
    checks = ReadinessChecks(database=database, cache=cache_status)
    is_ready = checks.database is HealthStatus.OK and checks.cache is HealthStatus.OK
    return ReadinessResponse(
        status=HealthStatus.OK if is_ready else HealthStatus.UNAVAILABLE, checks=checks
    )


async def _check_database(db: AsyncSession) -> HealthStatus:
    try:
        await db.execute(DATABASE_PING)
    except SQLAlchemyError:
        # The detail (host, user, driver message) goes to the log only: the
        # endpoint is unauthenticated, so the response just says "unavailable".
        logger.exception("health check: database ping failed")
        return HealthStatus.UNAVAILABLE
    return HealthStatus.OK


async def _check_cache(cache: Redis) -> HealthStatus:
    try:
        await cache.ping()
    except RedisError:
        logger.exception("health check: cache ping failed")
        return HealthStatus.UNAVAILABLE
    return HealthStatus.OK
