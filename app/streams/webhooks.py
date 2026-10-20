"""LiveKit's webhook: how the media server tells this API about rooms.

POST /webhooks/livekit    LiveKit reports rooms opening and closing and who comes and goes

Only LiveKit can call it: the body must carry its signature (livekit.py).
Notices end streams whose room closed, track the commentator's connection,
and start the HLS recording (service.apply_room_notice).
"""

import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import Settings, get_settings
from app.common.db import get_db
from app.common.request_body import read_limited_body
from app.common.schema import documented_errors
from app.streams import service
from app.streams.errors import WebhookPayloadError, WebhookSignatureError
from app.streams.livekit import verify_webhook
from app.streams.recorder import Recorder, get_recorder

logger = logging.getLogger(__name__)

webhooks_router = APIRouter(tags=["webhooks"])

# LiveKit's notices are a few kilobytes; anything far bigger isn't one.
MAX_WEBHOOK_BYTES = 64 * 1024


@webhooks_router.post(
    "/livekit",
    status_code=HTTPStatus.NO_CONTENT,
    responses=documented_errors(
        HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED, HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    ),
)
async def livekit_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    recorder: Annotated[Recorder | None, Depends(get_recorder)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Only LiveKit can call this: the body must carry its signature."""
    body = await read_limited_body(request, MAX_WEBHOOK_BYTES)
    try:
        notice = verify_webhook(
            body,
            authorization,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret.get_secret_value(),
        )
    except WebhookSignatureError as error:
        logger.warning("livekit webhook rejected: %s", error)
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "Invalid webhook signature") from error
    except WebhookPayloadError as error:
        logger.warning("livekit webhook unreadable: %s", error)
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Unreadable webhook") from error
    await service.apply_room_notice(db, notice, now=datetime.now(UTC), recorder=recorder)
