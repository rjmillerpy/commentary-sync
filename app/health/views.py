"""Health endpoints for load balancers, orchestrators and Docker healthchecks.

GET /health/live  liveness: the process is up and serving requests.
GET /health       readiness: the app can do real work (the database and Redis
                  answer). 503 tells a load balancer to stop sending traffic here.

Both are unauthenticated and uncached. What each one checks lives in
service.py; this module only maps the result onto HTTP.
"""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.cache import get_cache
from app.common.db import get_db
from app.common.http_headers import CACHE_CONTROL_HEADER, NO_STORE
from app.health import service
from app.health.schema import HealthStatus, LivenessResponse, ReadinessResponse

health_router = APIRouter(tags=["health"])

# Health responses describe this instant; nothing in between may cache them.


@health_router.get("/live")
async def live(response: Response) -> LivenessResponse:
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return service.liveness()


@health_router.get(
    "", responses={HTTPStatus.SERVICE_UNAVAILABLE.value: {"model": ReadinessResponse}}
)
async def ready(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    cache: Annotated[Redis, Depends(get_cache)],
) -> ReadinessResponse:
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    result = await service.readiness(db, cache)
    if result.status is not HealthStatus.OK:
        response.status_code = HTTPStatus.SERVICE_UNAVAILABLE
    return result
