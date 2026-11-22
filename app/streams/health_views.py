"""How a commentator's listeners are syncing, for their studio.

GET /streams/{id}/sync-health  the commentator's own live stream only

Apart from views.py to keep both under the module size limit.
"""

import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.common.cache import get_cache
from app.common.db import get_db
from app.common.rate_limit import RateLimit, rate_limited
from app.common.schema import documented_errors
from app.streams import service, sync_health
from app.streams.errors import StreamEndedError, StreamNotFoundError
from app.streams.schema import SyncHealth
from app.streams.views import STREAM_ENDED_DETAIL, STREAM_NOT_FOUND_DETAIL

sync_health_router = APIRouter(tags=["streams"])

# The studio asks every 10 s; room to spare for a reload or two.
HEALTH_READS_PER_MINUTE = RateLimit("stream-sync-health-minute", limit=20, window_seconds=60)


@sync_health_router.get(
    "/{stream_id}/sync-health",
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ),
    dependencies=[Depends(rate_limited(HEALTH_READS_PER_MINUTE))],
)
async def sync_health_of(
    stream_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cache: Annotated[Redis, Depends(get_cache)],
) -> SyncHealth:
    try:
        stream = await service.own_live_stream(db, user, stream_id)
    except StreamNotFoundError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, STREAM_NOT_FOUND_DETAIL) from error
    except StreamEndedError as error:
        raise HTTPException(HTTPStatus.CONFLICT, STREAM_ENDED_DETAIL) from error
    health = await sync_health.summary(cache, stream.id, now=datetime.now(UTC).timestamp())
    if health is None:
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Try again shortly")
    return SyncHealth(
        in_sync=health.in_sync,
        not_heard=health.not_heard,
        typical_delay_seconds=health.typical_delay_seconds,
    )
