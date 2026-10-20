"""HTTP endpoints for events: what listeners browse to pick a game.

GET /events             one page of upcoming and live events, by start time
GET /events/{event_id}  one event
"""

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import get_db
from app.common.pagination import DEFAULT_PAGE_SIZE, PageLimit, PageOffset
from app.common.schema import documented_errors
from app.events import service
from app.events.errors import EventNotFoundError
from app.events.models import Event
from app.events.schema import EventPage, EventResponse, League

events_router = APIRouter(tags=["events"])


@events_router.get("")
async def list_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    league: League | None = None,
    starts_after: Annotated[
        datetime | None, Query(description="Default: four hours ago, so live games show.")
    ] = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> EventPage:
    events = await service.list_events(
        db, league=league, starts_after=starts_after, limit=limit, offset=offset
    )
    return EventPage.build([_to_response(event) for event in events], limit=limit, offset=offset)


@events_router.get("/{event_id}", responses=documented_errors(HTTPStatus.NOT_FOUND))
async def get_event(
    event_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> EventResponse:
    try:
        event = await service.get_event(db, event_id)
    except EventNotFoundError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="Event not found") from error
    return _to_response(event)


def _to_response(event: Event) -> EventResponse:
    return EventResponse.model_validate(event, from_attributes=True)
