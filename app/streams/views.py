"""HTTP endpoints for streams.

POST /streams             the signed-in commentator goes live on an event
POST /streams/{id}/end    end one of your own streams
POST /streams/{id}/publisher-token  the stream's commentator: join its audio room to send
POST /streams/{id}/listener-token   any signed-in account: join a live stream's room to hear
POST /streams/{id}/listener-playlist  any signed-in account: the stream's HLS, to hear it delayed
POST /streams/{id}/reference  the stream's commentator: a chunk of their room audio, for sync
POST /streams/{id}/sync       any signed-in account: features of their TV's sound; how far to delay
POST /streams/{id}/listening  any signed-in account: "I'm listening", every 20 s while playing
GET  /streams             one page of live streams, optionally for one event or commentator
GET  /streams/{id}        one stream, live or ended

LiveKit's webhook is in webhooks.py.
"""

import logging
import uuid
from collections.abc import Awaitable, Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.commentators.errors import NotACommentatorError
from app.commentators.models import MAX_HANDLE_LENGTH
from app.common.cache import get_cache
from app.common.config import Settings, get_settings
from app.common.db import get_db
from app.common.http_headers import CACHE_CONTROL_HEADER, NO_STORE
from app.common.pagination import DEFAULT_PAGE_SIZE, PageLimit, PageOffset
from app.common.rate_limit import RateLimit, rate_limited
from app.common.request_body import read_limited_body
from app.common.schema import documented_errors
from app.events.errors import EventNotFoundError
from app.streams import audience, reference, service, tv_sync
from app.streams.errors import (
    AlreadyLiveError,
    CaptureTimeError,
    EventOverError,
    NotRecordingError,
    StreamEndedError,
    StreamNotFoundError,
    SyncAudioError,
)
from app.streams.models import Stream
from app.streams.recorder import Recorder, get_recorder
from app.streams.schema import (
    GoLive,
    PlaylistAccess,
    RoomAccess,
    StreamCommentator,
    StreamPage,
    StreamResponse,
    StreamStatus,
    SyncResult,
)

logger = logging.getLogger(__name__)

streams_router = APIRouter(tags=["streams"])

STREAM_NOT_FOUND_DETAIL = "Stream not found"
STREAM_ENDED_DETAIL = "This stream has already ended"
# Per client IP. A client needs one token per join, and LiveKit reconnects
# without a new one, so a person never comes near this.
ROOM_TOKENS_PER_MINUTE = RateLimit("stream-room-token-minute", limit=30, window_seconds=60)
ROOM_TOKEN_ERRORS = documented_errors(
    HTTPStatus.UNAUTHORIZED, HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT, HTTPStatus.TOO_MANY_REQUESTS
)

# The studio sends a reference chunk every few seconds; a listener syncs now
# and then, and each sync decodes and searches minutes of audio.
REFERENCE_CHUNKS_PER_MINUTE = RateLimit("stream-reference-minute", limit=30, window_seconds=60)
SYNCS_PER_MINUTE = RateLimit("stream-sync-minute", limit=12, window_seconds=60)
# An app checks in 3 times a minute; a household of listeners shares an address.
CHECK_INS_PER_MINUTE = RateLimit("stream-listening-minute", limit=30, window_seconds=60)
# Going live and ending: a commentator does each a few times a game.
STREAM_CHANGES_PER_MINUTE = RateLimit("stream-change-minute", limit=10, window_seconds=60)
# Both take raw bytes, not JSON; described for the OpenAPI document by hand.
AUDIO_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}
SYNC_ERRORS = documented_errors(
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.CONFLICT,
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    HTTPStatus.TOO_MANY_REQUESTS,
)


Database = Annotated[AsyncSession, Depends(get_db)]
SignedIn = Annotated[User, Depends(current_user)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
CurrentRecorder = Annotated[Recorder | None, Depends(get_recorder)]
Cache = Annotated[Redis, Depends(get_cache)]
CapturedAt = Annotated[
    float,
    Query(description="When the audio's first sample was captured: server time, epoch seconds"),
]


@streams_router.post(
    "",
    status_code=HTTPStatus.CREATED,
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.TOO_MANY_REQUESTS,
    ),
    dependencies=[Depends(rate_limited(STREAM_CHANGES_PER_MINUTE))],
)
async def go_live(request: GoLive, user: SignedIn, db: Database) -> StreamResponse:
    try:
        stream = await service.go_live(db, user, request, now=datetime.now(UTC))
    except NotACommentatorError as error:
        raise HTTPException(HTTPStatus.FORBIDDEN, "Only commentators can go live") from error
    except EventNotFoundError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Event not found") from error
    except EventOverError as error:
        raise HTTPException(HTTPStatus.CONFLICT, "This event is over") from error
    except AlreadyLiveError as error:
        raise HTTPException(
            HTTPStatus.CONFLICT, "You are already live; end that stream first"
        ) from error
    return _to_response(stream, listeners=0)


@streams_router.post(
    "/{stream_id}/end",
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.TOO_MANY_REQUESTS,
    ),
    dependencies=[Depends(rate_limited(STREAM_CHANGES_PER_MINUTE))],
)
async def end_stream(
    stream_id: uuid.UUID, user: SignedIn, db: Database, recorder: CurrentRecorder
) -> StreamResponse:
    stream = await _on_live_stream(
        service.end_stream(db, user, stream_id, now=datetime.now(UTC), recorder=recorder)
    )
    return _to_response(stream, listeners=0)


@streams_router.post(
    "/{stream_id}/publisher-token",
    responses=ROOM_TOKEN_ERRORS,
    dependencies=[Depends(rate_limited(ROOM_TOKENS_PER_MINUTE))],
)
async def publisher_token(
    stream_id: uuid.UUID,
    user: SignedIn,
    db: Database,
    settings: CurrentSettings,
    response: Response,
) -> RoomAccess:
    access = await _on_live_stream(
        service.publisher_access(db, user, stream_id, settings, now=datetime.now(UTC))
    )
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # it carries a token
    return access


@streams_router.post(
    "/{stream_id}/listener-token",
    responses=ROOM_TOKEN_ERRORS,
    dependencies=[Depends(rate_limited(ROOM_TOKENS_PER_MINUTE))],
)
async def listener_token(
    stream_id: uuid.UUID,
    user: SignedIn,
    db: Database,
    settings: CurrentSettings,
    response: Response,
) -> RoomAccess:
    access = await _on_live_stream(
        service.listener_access(db, user, stream_id, settings, now=datetime.now(UTC))
    )
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # it carries a token
    return access


@streams_router.post(
    "/{stream_id}/listener-playlist",
    responses=ROOM_TOKEN_ERRORS,
    # Signed in like a token, for the same reason: the URL is the only key.
    dependencies=[Depends(current_user), Depends(rate_limited(ROOM_TOKENS_PER_MINUTE))],
)
async def listener_playlist(
    stream_id: uuid.UUID, db: Database, settings: CurrentSettings, response: Response
) -> PlaylistAccess:
    try:
        access = await _on_live_stream(service.listener_playlist(db, stream_id, settings))
    except NotRecordingError as error:
        # Until the commentator's audio connects; a client tries again shortly.
        raise HTTPException(HTTPStatus.CONFLICT, "This stream has no HLS audio yet") from error
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE
    return access


@streams_router.post(
    "/{stream_id}/reference",
    status_code=HTTPStatus.NO_CONTENT,
    responses=SYNC_ERRORS,
    openapi_extra=AUDIO_BODY,
    dependencies=[Depends(rate_limited(REFERENCE_CHUNKS_PER_MINUTE))],
)
async def add_reference(
    stream_id: uuid.UUID,
    captured_at: CapturedAt,
    request: Request,
    user: SignedIn,
    db: Database,
    cache: Cache,
    settings: CurrentSettings,
) -> None:
    """16-bit little-endian mono PCM at 8 kHz, up to 10 s: the commentator's room."""
    pcm = await read_limited_body(request, reference.MAX_CHUNK_BYTES)
    action = tv_sync.add_reference(
        db, cache, user, stream_id, captured_at, pcm, settings, now=datetime.now(UTC)
    )
    await _with_sync_errors(_on_live_stream(action))


@streams_router.post(
    "/{stream_id}/sync",
    responses=SYNC_ERRORS,
    openapi_extra=AUDIO_BODY,
    dependencies=[Depends(current_user), Depends(rate_limited(SYNCS_PER_MINUTE))],
)
async def sync_to_tv(
    stream_id: uuid.UUID, captured_at: CapturedAt, request: Request, db: Database, cache: Cache
) -> SyncResult:
    """The matcher's features of 3 to 20 s of the listener's TV (client/src/features.ts):
    frames of 16 little-endian float32 values, 100 a second. Never audio."""
    features = await read_limited_body(request, tv_sync.MAX_FEATURE_BYTES)
    action = tv_sync.measure_delay(
        db, cache, stream_id, features, captured_at, now=datetime.now(UTC)
    )
    return await _with_sync_errors(_on_live_stream(action))


@streams_router.post(
    "/{stream_id}/listening",
    status_code=HTTPStatus.NO_CONTENT,
    responses=documented_errors(
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ),
    dependencies=[Depends(rate_limited(CHECK_INS_PER_MINUTE))],
)
async def check_in(
    stream_id: uuid.UUID, user: SignedIn, db: Database, cache: Cache, settings: CurrentSettings
) -> None:
    stream = await _on_live_stream(service.live_stream(db, stream_id))
    try:
        await audience.check_in(
            cache,
            stream.id,
            user.id,
            now=datetime.now(UTC).timestamp(),
            window_seconds=settings.listener_window_seconds,
        )
    except RedisError as error:
        raise HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Try again shortly") from error


@streams_router.get("")
async def list_live_streams(
    db: Database,
    cache: Cache,
    settings: CurrentSettings,
    event_id: uuid.UUID | None = None,
    commentator: Annotated[str | None, Query(max_length=MAX_HANDLE_LENGTH)] = None,
    limit: PageLimit = DEFAULT_PAGE_SIZE,
    offset: PageOffset = 0,
) -> StreamPage:
    streams = await service.list_live(
        db, event_id=event_id, handle=commentator, limit=limit, offset=offset
    )
    counts = await _listener_counts(cache, settings, streams)
    return StreamPage.build(
        [_to_response(stream, counts) for stream in streams], limit=limit, offset=offset
    )


@streams_router.get("/{stream_id}", responses=documented_errors(HTTPStatus.NOT_FOUND))
async def get_stream(
    stream_id: uuid.UUID, db: Database, cache: Cache, settings: CurrentSettings
) -> StreamResponse:
    try:
        stream = await service.get_stream(db, stream_id)
    except StreamNotFoundError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, STREAM_NOT_FOUND_DETAIL) from error
    if stream.ended_at is not None:
        return _to_response(stream, listeners=0)
    return _to_response(stream, await _listener_counts(cache, settings, [stream]))


async def _on_live_stream[Result](action: Awaitable[Result]) -> Result:
    """Run an action on one live stream, mapping its two failures to HTTP."""
    try:
        return await action
    except StreamNotFoundError as error:
        raise HTTPException(HTTPStatus.NOT_FOUND, STREAM_NOT_FOUND_DETAIL) from error
    except StreamEndedError as error:
        raise HTTPException(HTTPStatus.CONFLICT, STREAM_ENDED_DETAIL) from error


async def _with_sync_errors[Result](action: Awaitable[Result]) -> Result:
    """Audio sync's own failures are the client's: 400, with what was wrong."""
    try:
        return await action
    except (SyncAudioError, CaptureTimeError) as error:
        raise HTTPException(HTTPStatus.BAD_REQUEST, str(error)) from error


async def _listener_counts(
    cache: Redis, settings: Settings, streams: Sequence[Stream]
) -> dict[uuid.UUID, int] | None:
    return await audience.count(
        cache,
        [stream.id for stream in streams],
        now=datetime.now(UTC).timestamp(),
        window_seconds=settings.listener_window_seconds,
    )


def _to_response(
    stream: Stream, counts: dict[uuid.UUID, int] | None = None, *, listeners: int | None = None
) -> StreamResponse:
    """`listeners` if given, else this stream's entry in `counts` (None when
    counts are unavailable)."""
    if listeners is None and counts is not None:
        listeners = counts.get(stream.id, 0)
    return StreamResponse(
        id=stream.id,
        event_id=stream.event_id,
        commentator=StreamCommentator(
            handle=stream.commentator.handle,
            display_name=stream.commentator.user.display_name,
        ),
        status=StreamStatus.LIVE if stream.ended_at is None else StreamStatus.ENDED,
        started_at=stream.started_at,
        ended_at=stream.ended_at,
        listeners=listeners,
    )
