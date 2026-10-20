"""Streams: a commentator goes live on an event, listeners find who is live."""

import logging
import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import Select, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.models import User
from app.commentators import service as commentators
from app.commentators.models import Commentator
from app.common.config import Settings
from app.events import service as events
from app.events.models import Event
from app.events.schema import EventStatus
from app.streams.errors import (
    AlreadyLiveError,
    EventOverError,
    NotRecordingError,
    RecorderError,
    StreamEndedError,
    StreamNotFoundError,
)
from app.streams.livekit import (
    RoomGrant,
    RoomRole,
    create_room_token,
    publisher_identity,
    room_name,
    stream_id_from_room,
)
from app.streams.models import HLS_PATH_BYTES, Stream
from app.streams.recorder import Recorder, playlist_url
from app.streams.schema import (
    GoLive,
    NoticeParticipant,
    PlaylistAccess,
    RoomAccess,
    RoomEvent,
    RoomNotice,
)

logger = logging.getLogger(__name__)

# Final, cancelled and postponed games have nothing left to commentate.
OPEN_EVENT_STATUSES = frozenset({EventStatus.SCHEDULED, EventStatus.LIVE})


async def go_live(db: AsyncSession, user: User, request: GoLive, *, now: datetime) -> Stream:
    """Start the account's commentator on an event.

    Raises NotACommentatorError and EventNotFoundError from their domains,
    EventOverError, and AlreadyLiveError while another stream is live.
    """
    commentator = await commentators.get_own_profile(db, user.id)
    event = await events.get_event(db, request.event_id)
    if event.status not in OPEN_EVENT_STATUSES:
        raise EventOverError(f"event is {event.status}")
    stream = Stream(commentator=commentator, event_id=event.id, started_at=now)
    db.add(stream)
    # The partial unique index decides, not a SELECT first: two "go live"
    # requests racing would both pass a SELECT.
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise AlreadyLiveError("commentator already has a live stream") from error
    await db.commit()
    logger.info(
        "stream %s live", stream.id, extra={"stream_id": str(stream.id), "event_id": str(event.id)}
    )
    return stream


async def end_stream(
    db: AsyncSession,
    user: User,
    stream_id: uuid.UUID,
    *,
    now: datetime,
    recorder: Recorder | None = None,
) -> Stream:
    """End one of the account's own streams, and its recording."""
    stream = _live(await _own_stream(db, user, stream_id))
    stream.ended_at = now
    await db.commit()
    logger.info("stream %s ended", stream.id, extra={"stream_id": str(stream.id)})
    if recorder is not None and stream.recording_id is not None:
        await _stop_recording(recorder, stream.id, stream.recording_id, now)
    return stream


async def publisher_access(
    db: AsyncSession, user: User, stream_id: uuid.UUID, settings: Settings, *, now: datetime
) -> RoomAccess:
    """A token that lets the stream's own commentator send audio to its room."""
    stream = _live(await _own_stream(db, user, stream_id))
    grant = RoomGrant(
        room=room_name(stream.id),
        identity=publisher_identity(stream.commentator.id),
        role=RoomRole.PUBLISHER,
        display_name=stream.commentator.handle,
    )
    return _room_access(stream, grant, settings, now)


async def listener_access(
    db: AsyncSession, user: User, stream_id: uuid.UUID, settings: Settings, *, now: datetime
) -> RoomAccess:
    """A token that lets a signed-in account hear a live stream."""
    stream = _live(await get_stream(db, stream_id))
    grant = RoomGrant(
        room=room_name(stream.id), identity=f"listener-{user.id}", role=RoomRole.LISTENER
    )
    return _room_access(stream, grant, settings, now)


async def listener_playlist(
    db: AsyncSession, stream_id: uuid.UUID, settings: Settings
) -> PlaylistAccess:
    """Where a signed-in account plays a live stream's HLS recording.
    Raises NotRecordingError until the recording has started."""
    stream = _live(await get_stream(db, stream_id))
    if settings.hls_base_url is None or stream.recording_id is None or stream.hls_path is None:
        raise NotRecordingError("stream has no HLS recording yet")
    logger.info("playlist issued for stream %s", stream.id, extra={"stream_id": str(stream.id)})
    return PlaylistAccess(url=playlist_url(str(settings.hls_base_url), stream.hls_path))


async def apply_room_notice(
    db: AsyncSession, notice: RoomNotice, *, now: datetime, recorder: Recorder | None = None
) -> None:
    """Track the commentator's audio connection from a LiveKit webhook.

    The room closing ends the stream at once: nobody, commentator or listener,
    is left in it (its recording ends with it). The commentator leaving only
    marks the time, and end_abandoned_streams ends the stream if they don't
    come back. The commentator's first join starts the HLS recording.
    Notices for other rooms, other participants and ended streams change nothing.
    """
    stream_id = stream_id_from_room(notice.room.name) if notice.room else None
    stream = await _find(db, stream_id) if stream_id else None
    if stream is None or stream.ended_at is not None:
        return
    is_publisher = notice.participant is not None and _is_publisher(stream, notice.participant)
    if notice.event == RoomEvent.ROOM_FINISHED:
        stream.ended_at = now
        logger.info("stream %s ended: room closed", stream.id, extra={"stream_id": str(stream.id)})
    elif notice.participant is not None and is_publisher:
        _track_publisher(stream, notice.event, notice.participant, now)
    needs_recording = is_publisher and notice.event == RoomEvent.PARTICIPANT_JOINED
    await db.commit()
    if recorder is not None and needs_recording and stream.hls_path is None:
        await _start_recording(db, recorder, stream.id, now)


async def end_abandoned_streams(
    db: AsyncSession,
    *,
    now: datetime,
    audio_grace: timedelta,
    recorder: Recorder | None = None,
) -> list[uuid.UUID]:
    """End live streams whose event is over or whose commentator's audio has
    been gone longer than `audio_grace`, and their recordings. Returns the IDs
    it ended."""
    event_over = select(Event.id).where(Event.status.not_in(OPEN_EVENT_STATUSES))
    abandoned = or_(Stream.event_id.in_(event_over), Stream.publisher_left_at <= now - audio_grace)
    statement = (
        update(Stream)
        .where(Stream.ended_at.is_(None), abandoned)
        .values(ended_at=now)
        .returning(Stream.id, Stream.recording_id)
    )
    ended = list((await db.execute(statement)).all())
    await db.commit()
    for stream_id, recording_id in ended:
        logger.info("stream %s ended: abandoned", stream_id, extra={"stream_id": str(stream_id)})
        if recorder is not None and recording_id is not None:
            await _stop_recording(recorder, stream_id, recording_id, now)
    return [stream_id for stream_id, _ in ended]


async def get_stream(db: AsyncSession, stream_id: uuid.UUID) -> Stream:
    stream = await _find(db, stream_id)
    if stream is None:
        raise StreamNotFoundError("no such stream")
    return stream


async def list_live(
    db: AsyncSession,
    *,
    event_id: uuid.UUID | None,
    limit: int,
    offset: int,
    handle: str | None = None,
) -> Sequence[Stream]:
    """Live streams, longest-running first, each with its commentator, in one
    query; for one event, one commentator (by handle, any case), or both."""
    query = _with_commentator().where(Stream.ended_at.is_(None))
    if event_id is not None:
        query = query.where(Stream.event_id == event_id)
    if handle is not None:
        # An explicit join: joinedload's own is aliased, so filtering on
        # Commentator without one would cross-join the table.
        query = query.join(Stream.commentator).where(Commentator.handle == handle.lower())
    query = query.order_by(Stream.started_at, Stream.id).limit(limit).offset(offset)
    return (await db.execute(query)).scalars().all()


async def own_live_stream(db: AsyncSession, user: User, stream_id: uuid.UUID) -> Stream:
    """One of the account's own streams, if it is live. Raises
    StreamNotFoundError (also for someone else's) and StreamEndedError."""
    return _live(await _own_stream(db, user, stream_id))


async def live_stream(db: AsyncSession, stream_id: uuid.UUID) -> Stream:
    """Any stream, if it is live. Raises StreamNotFoundError and StreamEndedError."""
    return _live(await get_stream(db, stream_id))


async def _own_stream(db: AsyncSession, user: User, stream_id: uuid.UUID) -> Stream:
    stream = await _find(db, stream_id)
    # Someone else's stream gets the same answer as a missing one, so stream
    # IDs can't be probed for who owns them.
    if stream is None or stream.commentator.user_id != user.id:
        raise StreamNotFoundError("no such stream for this account")
    return stream


def _is_publisher(stream: Stream, participant: NoticeParticipant) -> bool:
    return participant.identity == publisher_identity(stream.commentator_id)


def _track_publisher(
    stream: Stream, event: str, participant: NoticeParticipant, now: datetime
) -> None:
    """A join is the commentator's newest connection. A leave counts only for
    that connection: a reload's new connection can join before the old one
    leaves. With no join seen (its webhook was lost), any leave counts."""
    if event == RoomEvent.PARTICIPANT_JOINED:
        stream.publisher_sid = participant.sid
        stream.publisher_left_at = None
    elif event == RoomEvent.PARTICIPANT_LEFT and stream.publisher_sid in (None, participant.sid):
        stream.publisher_left_at = now
    else:
        return
    logger.info(
        "stream %s commentator audio: %s",
        stream.id,
        event,
        extra={"stream_id": str(stream.id), "room_event": event},
    )


async def _start_recording(
    db: AsyncSession, recorder: Recorder, stream_id: uuid.UUID, now: datetime
) -> None:
    """Start the stream's HLS recording, once.

    The path is claimed in the database first: a reload's join can arrive
    while the first join's start is still in flight, and only one claim
    succeeds. A failed start gives the claim back, so the next join retries;
    meanwhile listeners still have WebRTC.
    """
    hls_path = secrets.token_urlsafe(HLS_PATH_BYTES)
    claim = (
        update(Stream)
        .where(Stream.id == stream_id, Stream.hls_path.is_(None), Stream.ended_at.is_(None))
        .values(hls_path=hls_path)
        .returning(Stream.id)
    )
    claimed = (await db.execute(claim)).scalar_one_or_none() is not None
    await db.commit()
    if not claimed:
        return
    try:
        recording_id = await recorder.start(room_name(stream_id), hls_path, now=now)
    except RecorderError:
        logger.warning(
            "stream %s: recording did not start",
            stream_id,
            exc_info=True,
            extra={"stream_id": str(stream_id)},
        )
        recording_id = None
    values = {"recording_id": recording_id} if recording_id else {"hls_path": None}
    await db.execute(update(Stream).where(Stream.id == stream_id).values(**values))
    await db.commit()
    if recording_id:
        logger.info("stream %s recording", stream_id, extra={"stream_id": str(stream_id)})


async def _stop_recording(
    recorder: Recorder, stream_id: uuid.UUID, recording_id: str, now: datetime
) -> None:
    """Stop a recording; a failure is logged, not raised. The stream has
    already ended, and the recording ends anyway when the room closes."""
    try:
        await recorder.stop(recording_id, now=now)
    except RecorderError:
        logger.warning(
            "stream %s: recording did not stop",
            stream_id,
            exc_info=True,
            extra={"stream_id": str(stream_id)},
        )


def _live(stream: Stream) -> Stream:
    if stream.ended_at is not None:
        raise StreamEndedError("stream already ended")
    return stream


def _room_access(stream: Stream, grant: RoomGrant, settings: Settings, now: datetime) -> RoomAccess:
    token = create_room_token(
        grant,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret.get_secret_value(),
        lifetime=timedelta(seconds=settings.livekit_token_seconds),
        now=now,
    )
    logger.info(
        "room token issued for stream %s",
        stream.id,
        extra={"stream_id": str(stream.id), "room_role": grant.role.value},
    )
    return RoomAccess(
        url=str(settings.livekit_url),
        room=grant.room,
        token=token,
        expires_in=settings.livekit_token_seconds,
    )


async def _find(db: AsyncSession, stream_id: uuid.UUID) -> Stream | None:
    query = _with_commentator().where(Stream.id == stream_id)
    return (await db.execute(query)).scalar_one_or_none()


def _with_commentator() -> Select[Stream]:
    """Streams joined to their commentators and accounts, which every response needs."""
    return select(Stream).options(joinedload(Stream.commentator).joinedload(Commentator.user))
