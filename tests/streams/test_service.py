import logging
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import jwt
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.commentators.errors import NotACommentatorError
from app.common.config import Settings
from app.events.errors import EventNotFoundError
from app.events.models import Event
from app.events.schema import EventStatus
from app.streams import service
from app.streams.errors import (
    AlreadyLiveError,
    EventOverError,
    NotRecordingError,
    StreamEndedError,
    StreamNotFoundError,
)
from app.streams.models import HLS_PATH_LENGTH, Stream
from app.streams.recorder import Recorder
from app.streams.schema import GoLive, NoticeParticipant, NoticeRoom, RoomAccess, RoomNotice
from tests.conftest import TEST_LIVEKIT_API_SECRET, TEST_LIVEKIT_URL
from tests.streams.conftest import (
    NOW,
    START,
    STOP,
    TEST_HLS_BASE_URL,
    FakeEgress,
    add_commentator,
    add_event,
    add_user,
)

pytestmark = pytest.mark.anyio

LATER = NOW + timedelta(hours=3)
GRACE = timedelta(minutes=2)


async def test_going_live_starts_a_stream_on_the_event(db: AsyncSession, event: Event) -> None:
    user = await add_commentator(db)
    stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    assert (stream.event_id, stream.started_at, stream.ended_at) == (event.id, NOW, None)
    assert stream.commentator.handle == "fan_cast"
    assert stream.commentator.user.display_name == "Fan"


@pytest.mark.parametrize(
    "status", [EventStatus.SCHEDULED, EventStatus.LIVE], ids=["before-kickoff", "in-progress"]
)
async def test_open_events_can_be_commentated(db: AsyncSession, status: EventStatus) -> None:
    user = await add_commentator(db)
    event = await add_event(db, status)
    await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)


@pytest.mark.parametrize(
    "status",
    [EventStatus.FINAL, EventStatus.CANCELLED, EventStatus.POSTPONED],
    ids=["final", "cancelled", "postponed"],
)
async def test_closed_events_cant_be_commentated(db: AsyncSession, status: EventStatus) -> None:
    user = await add_commentator(db)
    event = await add_event(db, status)
    with pytest.raises(EventOverError):
        await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)


async def test_a_listener_cant_go_live(db: AsyncSession, event: Event) -> None:
    user = await add_user(db)
    with pytest.raises(NotACommentatorError):
        await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)


async def test_going_live_on_an_unknown_event_is_an_error(db: AsyncSession) -> None:
    user = await add_commentator(db)
    with pytest.raises(EventNotFoundError):
        await service.go_live(db, user, GoLive(event_id=uuid.uuid4()), now=NOW)


async def test_one_live_stream_at_a_time(db: AsyncSession, event: Event) -> None:
    user = await add_commentator(db)
    other_event = await add_event(db, source_id="402")
    await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    with pytest.raises(AlreadyLiveError):
        await service.go_live(db, user, GoLive(event_id=other_event.id), now=NOW)
    assert len(await service.list_live(db, event_id=None, limit=10, offset=0)) == 1


async def test_after_ending_a_stream_the_commentator_can_go_live_again(
    db: AsyncSession, event: Event
) -> None:
    user = await add_commentator(db)
    first = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    await service.end_stream(db, user, first.id, now=LATER)
    second = await service.go_live(db, user, GoLive(event_id=event.id), now=LATER)
    assert second.id != first.id


async def test_ending_sets_the_end_time(db: AsyncSession, event: Event) -> None:
    user = await add_commentator(db)
    stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    ended = await service.end_stream(db, user, stream.id, now=LATER)
    assert ended.ended_at == LATER


async def test_ending_twice_is_an_error(db: AsyncSession, event: Event) -> None:
    user = await add_commentator(db)
    stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    await service.end_stream(db, user, stream.id, now=LATER)
    with pytest.raises(StreamEndedError):
        await service.end_stream(db, user, stream.id, now=LATER)


async def test_nobody_can_end_someone_elses_stream(db: AsyncSession, event: Event) -> None:
    owner = await add_commentator(db)
    other = await add_commentator(db, "other@example.com", "other_cast")
    stream = await service.go_live(db, owner, GoLive(event_id=event.id), now=NOW)
    with pytest.raises(StreamNotFoundError):
        await service.end_stream(db, other, stream.id, now=LATER)
    assert (await service.get_stream(db, stream.id)).ended_at is None


@pytest.mark.parametrize("finder", ["get", "end"], ids=["get", "end"])
async def test_unknown_stream_is_an_error(db: AsyncSession, finder: str) -> None:
    user = await add_user(db)
    with pytest.raises(StreamNotFoundError):
        if finder == "get":
            await service.get_stream(db, uuid.uuid4())
        else:
            await service.end_stream(db, user, uuid.uuid4(), now=NOW)


async def test_live_list_filters_by_event_and_leaves_out_ended_streams(
    db: AsyncSession, event: Event
) -> None:
    other_event = await add_event(db, source_id="402")
    first = await add_commentator(db, "a@example.com", "alpha")
    second = await add_commentator(db, "b@example.com", "bravo")
    third = await add_commentator(db, "c@example.com", "charlie")
    await service.go_live(db, first, GoLive(event_id=event.id), now=NOW)
    await service.go_live(db, second, GoLive(event_id=other_event.id), now=NOW)
    ended = await service.go_live(db, third, GoLive(event_id=event.id), now=NOW)
    await service.end_stream(db, third, ended.id, now=LATER)

    on_event = await service.list_live(db, event_id=event.id, limit=10, offset=0)
    everywhere = await service.list_live(db, event_id=None, limit=10, offset=0)
    assert [stream.commentator.handle for stream in on_event] == ["alpha"]
    assert {stream.commentator.handle for stream in everywhere} == {"alpha", "bravo"}


async def test_live_list_is_longest_running_first_with_accounts_loaded(
    db: AsyncSession, event: Event
) -> None:
    """Rule 21: commentators and accounts come in the same query (lazy="raise" proves it)."""
    for minutes, handle in [(30, "late"), (0, "early"), (10, "middle")]:
        user = await add_commentator(db, f"{handle}@example.com", handle)
        await service.go_live(
            db, user, GoLive(event_id=event.id), now=NOW + timedelta(minutes=minutes)
        )
    db.expunge_all()
    streams = await service.list_live(db, event_id=event.id, limit=2, offset=0)
    assert [stream.commentator.handle for stream in streams] == ["early", "middle"]
    assert {stream.commentator.user.display_name for stream in streams} == {"Fan"}


async def test_live_list_finds_one_commentators_stream_in_any_case(
    db: AsyncSession, event: Event
) -> None:
    mine = await add_commentator(db, "mine@example.com", "fan_cast")
    other = await add_commentator(db, "other@example.com", "other_cast")
    stream = await service.go_live(db, mine, GoLive(event_id=event.id), now=NOW)
    await service.go_live(db, other, GoLive(event_id=event.id), now=NOW)
    found = await service.list_live(db, event_id=None, handle="Fan_Cast", limit=10, offset=0)
    assert [found_stream.id for found_stream in found] == [stream.id]
    assert found[0].commentator.handle == "fan_cast"
    nobody = await service.list_live(db, event_id=None, handle="nobody", limit=10, offset=0)
    assert nobody == []


async def test_going_live_and_ending_are_logged_by_id_only(
    db: AsyncSession, event: Event, caplog: pytest.LogCaptureFixture
) -> None:
    user = await add_commentator(db)
    with caplog.at_level(logging.INFO, logger=service.__name__):
        stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
        await service.end_stream(db, user, stream.id, now=LATER)
    messages = [r.getMessage() for r in caplog.records if r.name == service.__name__]
    assert messages == [
        f"stream {stream.id} live",
        f"stream {stream.id} ended",
    ]
    assert "fan@example.com" not in caplog.text


def room_claims(access: RoomAccess) -> dict[str, object]:
    claims: dict[str, object] = jwt.decode(
        access.token,
        TEST_LIVEKIT_API_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_nbf": False},
    )
    return claims


async def test_the_commentator_gets_a_publisher_token_for_the_stream_room(
    db: AsyncSession, event: Event, settings: Settings
) -> None:
    user = await add_commentator(db)
    stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    access = await service.publisher_access(db, user, stream.id, settings, now=NOW)
    assert (access.url, access.room) == (f"{TEST_LIVEKIT_URL}/", f"stream-{stream.id}")
    assert access.expires_in == settings.livekit_token_seconds
    claims = room_claims(access)
    assert claims["sub"] == f"commentator-{stream.commentator.id}"
    assert claims["video"]["canPublish"] is True  # type: ignore[index]


async def test_a_listener_gets_a_subscribe_only_token(
    db: AsyncSession, event: Event, settings: Settings
) -> None:
    owner = await add_commentator(db)
    listener = await add_user(db, "listener@example.com")
    stream = await service.go_live(db, owner, GoLive(event_id=event.id), now=NOW)
    access = await service.listener_access(db, listener, stream.id, settings, now=NOW)
    claims = room_claims(access)
    assert claims["sub"] == f"listener-{listener.id}"
    assert claims["video"]["room"] == f"stream-{stream.id}"  # type: ignore[index]
    assert claims["video"]["canPublish"] is False  # type: ignore[index]


async def test_only_the_owner_gets_a_publisher_token(
    db: AsyncSession, event: Event, settings: Settings
) -> None:
    owner = await add_commentator(db)
    other = await add_commentator(db, "other@example.com", "other_cast")
    stream = await service.go_live(db, owner, GoLive(event_id=event.id), now=NOW)
    with pytest.raises(StreamNotFoundError):
        await service.publisher_access(db, other, stream.id, settings, now=NOW)


@pytest.mark.parametrize("role", ["publisher", "listener"], ids=["publisher", "listener"])
async def test_an_ended_stream_issues_no_tokens(
    db: AsyncSession, event: Event, settings: Settings, role: str
) -> None:
    user = await add_commentator(db)
    stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    await service.end_stream(db, user, stream.id, now=LATER)
    access = service.publisher_access if role == "publisher" else service.listener_access
    with pytest.raises(StreamEndedError):
        await access(db, user, stream.id, settings, now=LATER)


async def test_a_listener_token_for_an_unknown_stream_is_an_error(
    db: AsyncSession, settings: Settings
) -> None:
    user = await add_user(db)
    with pytest.raises(StreamNotFoundError):
        await service.listener_access(db, user, uuid.uuid4(), settings, now=NOW)


async def test_issuing_a_token_logs_the_stream_and_role_but_not_the_token(
    db: AsyncSession, event: Event, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    user = await add_commentator(db)
    stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
    with caplog.at_level(logging.INFO, logger=service.__name__):
        access = await service.publisher_access(db, user, stream.id, settings, now=NOW)
    records = [record for record in caplog.records if record.name == service.__name__]
    assert records[-1].getMessage() == f"room token issued for stream {stream.id}"
    assert records[-1].room_role == "publisher"  # type: ignore[attr-defined]
    assert access.token not in caplog.text


def room_notice(event: str, stream: Stream, participant: str | None = None) -> RoomNotice:
    """`participant` is "<identity>/<sid>"."""
    who = None
    if participant is not None:
        identity, sid = participant.split("/")
        who = NoticeParticipant(sid=sid, identity=identity)
    return RoomNotice(event=event, room=NoticeRoom(name=f"stream-{stream.id}"), participant=who)


def commentator(stream: Stream, sid: str = "PA_one") -> str:
    return f"commentator-{stream.commentator_id}/{sid}"


async def live_stream(db: AsyncSession, event: Event) -> Stream:
    user = await add_commentator(db)
    return await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)


def utc(stored: datetime | None) -> datetime | None:
    """SQLite hands timestamps back without their zone; they were written in UTC."""
    return None if stored is None else stored.replace(tzinfo=UTC)


async def reloaded(db: AsyncSession, stream: Stream) -> Stream:
    db.expunge_all()
    return await service.get_stream(db, stream.id)


async def test_the_commentator_dropping_marks_when(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(
        db, room_notice("participant_joined", stream, commentator(stream)), now=NOW
    )
    await service.apply_room_notice(
        db, room_notice("participant_left", stream, commentator(stream)), now=LATER
    )
    stream = await reloaded(db, stream)
    assert (stream.publisher_sid, utc(stream.publisher_left_at), utc(stream.ended_at)) == (
        "PA_one",
        LATER,
        None,
    )


async def test_the_commentator_coming_back_clears_it(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    for notice in ("participant_joined", "participant_left"):
        await service.apply_room_notice(
            db, room_notice(notice, stream, commentator(stream)), now=NOW
        )
    back = room_notice("participant_joined", stream, commentator(stream, "PA_two"))
    await service.apply_room_notice(db, back, now=LATER)
    stream = await reloaded(db, stream)
    assert (stream.publisher_sid, utc(stream.publisher_left_at)) == ("PA_two", None)


async def test_a_reload_doesnt_count_as_dropping(db: AsyncSession, event: Event) -> None:
    """The new connection joins before LiveKit drops the old one."""
    stream = await live_stream(db, event)
    first, second = commentator(stream, "PA_one"), commentator(stream, "PA_two")
    await service.apply_room_notice(db, room_notice("participant_joined", stream, first), now=NOW)
    await service.apply_room_notice(db, room_notice("participant_joined", stream, second), now=NOW)
    await service.apply_room_notice(db, room_notice("participant_left", stream, first), now=NOW)
    stream = await reloaded(db, stream)
    assert (stream.publisher_sid, utc(stream.publisher_left_at)) == ("PA_two", None)


async def test_dropping_counts_even_if_the_join_was_missed(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(
        db, room_notice("participant_left", stream, commentator(stream)), now=LATER
    )
    assert utc((await reloaded(db, stream)).publisher_left_at) == LATER


@pytest.mark.parametrize(
    "participant",
    ["listener-1/PA_x", "commentator-00000000-0000-0000-0000-000000000000/PA_x"],
    ids=["listener", "another-commentator"],
)
async def test_other_participants_change_nothing(
    db: AsyncSession, event: Event, participant: str
) -> None:
    stream = await live_stream(db, event)
    for notice in ("participant_joined", "participant_left"):
        await service.apply_room_notice(db, room_notice(notice, stream, participant), now=NOW)
    stream = await reloaded(db, stream)
    assert (stream.publisher_sid, utc(stream.publisher_left_at)) == (None, None)


async def test_other_events_change_nothing(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(
        db, room_notice("track_published", stream, commentator(stream)), now=NOW
    )
    stream = await reloaded(db, stream)
    assert (stream.publisher_sid, utc(stream.publisher_left_at), utc(stream.ended_at)) == (
        None,
        None,
        None,
    )


async def test_the_room_closing_ends_the_stream(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(db, room_notice("room_finished", stream), now=LATER)
    assert utc((await reloaded(db, stream)).ended_at) == LATER


async def test_an_ended_stream_stays_as_it_ended(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(db, room_notice("room_finished", stream), now=NOW)
    for notice in ("room_finished", "participant_left"):
        await service.apply_room_notice(
            db, room_notice(notice, stream, commentator(stream)), now=LATER
        )
    stream = await reloaded(db, stream)
    assert (utc(stream.ended_at), utc(stream.publisher_left_at)) == (NOW, None)


@pytest.mark.parametrize(
    "room",
    [None, NoticeRoom(name="lobby"), NoticeRoom(name=f"stream-{uuid.uuid4()}")],
    ids=["no-room", "foreign-room", "unknown-stream"],
)
async def test_notices_for_no_stream_are_ignored(
    db: AsyncSession, event: Event, room: NoticeRoom | None
) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(db, RoomNotice(event="room_finished", room=room), now=LATER)
    assert utc((await reloaded(db, stream)).ended_at) is None


async def drop_audio(db: AsyncSession, stream: Stream, at: datetime) -> None:
    notice = room_notice("participant_left", stream, commentator(stream))
    await service.apply_room_notice(db, notice, now=at)


@pytest.mark.parametrize(
    ("gone_for", "is_ended"),
    [(GRACE - timedelta(seconds=1), False), (GRACE, True), (GRACE * 10, True)],
    ids=["within-grace", "exactly-grace", "long-gone"],
)
async def test_streams_whose_audio_stays_gone_are_ended(
    db: AsyncSession, event: Event, gone_for: timedelta, is_ended: bool
) -> None:
    stream = await live_stream(db, event)
    await drop_audio(db, stream, NOW)
    ended = await service.end_abandoned_streams(db, now=NOW + gone_for, audio_grace=GRACE)
    assert ended == ([stream.id] if is_ended else [])
    expected_end = NOW + gone_for if is_ended else None
    assert utc((await reloaded(db, stream)).ended_at) == expected_end


@pytest.mark.parametrize(
    ("status", "is_ended"),
    [
        (EventStatus.LIVE, False),
        (EventStatus.SCHEDULED, False),
        (EventStatus.FINAL, True),
        (EventStatus.CANCELLED, True),
        (EventStatus.POSTPONED, True),
    ],
    ids=["live", "scheduled", "final", "cancelled", "postponed"],
)
async def test_streams_on_events_that_are_over_are_ended(
    db: AsyncSession, event: Event, status: EventStatus, is_ended: bool
) -> None:
    stream = await live_stream(db, event)
    event.status = status
    await db.commit()
    ended = await service.end_abandoned_streams(db, now=LATER, audio_grace=GRACE)
    assert ended == ([stream.id] if is_ended else [])


async def test_streams_already_ended_keep_their_end_time(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    await drop_audio(db, stream, NOW)
    await service.end_abandoned_streams(db, now=LATER, audio_grace=GRACE)
    assert await service.end_abandoned_streams(db, now=LATER + GRACE, audio_grace=GRACE) == []
    assert utc((await reloaded(db, stream)).ended_at) == LATER


async def test_room_notices_and_abandoned_streams_are_logged_by_id(
    db: AsyncSession, event: Event, caplog: pytest.LogCaptureFixture
) -> None:
    stream = await live_stream(db, event)
    with caplog.at_level(logging.INFO, logger=service.__name__):
        await drop_audio(db, stream, NOW)
        await service.end_abandoned_streams(db, now=LATER, audio_grace=GRACE)
    messages = [r.getMessage() for r in caplog.records if r.name == service.__name__]
    assert messages[-2:] == [
        f"stream {stream.id} commentator audio: participant_left",
        f"stream {stream.id} ended: abandoned",
    ]


async def commentator_joins(
    db: AsyncSession, stream: Stream, recorder: Recorder, sid: str = "PA_one"
) -> Stream:
    notice = room_notice("participant_joined", stream, commentator(stream, sid))
    await service.apply_room_notice(db, notice, now=NOW, recorder=recorder)
    return await reloaded(db, stream)


async def test_the_commentator_joining_starts_the_recording(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    assert stream.recording_id == "EG_test1"
    assert stream.hls_path is not None
    assert len(stream.hls_path) == HLS_PATH_LENGTH  # fits its column
    assert fake_egress.calls(START)[0]["room_name"] == f"stream-{stream.id}"
    prefix = fake_egress.calls(START)[0]["segment_outputs"]
    assert prefix == [
        {
            "filename_prefix": f"/hls/{stream.hls_path}/s",
            "playlist_name": "index.m3u8",
            "segment_duration": 2,
        }
    ]


async def test_a_reload_keeps_the_one_recording(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    """A room recording outlives the commentator's reconnects, so a second
    join starts nothing: listeners keep one playlist all game."""
    stream = await live_stream(db, event)
    first = await commentator_joins(db, stream, recorder, "PA_one")
    second = await commentator_joins(db, stream, recorder, "PA_two")
    assert len(fake_egress.calls(START)) == 1
    assert (second.recording_id, second.hls_path) == (first.recording_id, first.hls_path)


async def test_each_stream_records_to_its_own_unguessable_path(
    db: AsyncSession, recorder: Recorder
) -> None:
    """Security: the path is random, not the stream ID, so knowing a stream
    (which anyone can list) doesn't give its recording."""
    paths = set()
    for number in range(2):
        event = await add_event(db, source_id=f"40{number}")
        user = await add_commentator(db, f"caster{number}@example.com", f"caster_{number}")
        stream = await service.go_live(db, user, GoLive(event_id=event.id), now=NOW)
        recorded = await commentator_joins(db, stream, recorder)
        assert recorded.hls_path is not None
        assert str(stream.id) not in recorded.hls_path
        paths.add(recorded.hls_path)
    assert len(paths) == 2


async def test_a_failed_start_is_retried_on_the_next_join(
    db: AsyncSession,
    event: Event,
    recorder: Recorder,
    fake_egress: FakeEgress,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stream = await live_stream(db, event)
    fake_egress.failure = HTTPStatus.SERVICE_UNAVAILABLE
    with caplog.at_level(logging.WARNING, logger=service.__name__):
        failed = await commentator_joins(db, stream, recorder, "PA_one")
    assert (failed.recording_id, failed.hls_path) == (None, None)
    assert f"stream {stream.id}: recording did not start" in caplog.text
    fake_egress.failure = None
    retried = await commentator_joins(db, stream, recorder, "PA_two")
    assert retried.recording_id == "EG_test2"


@pytest.mark.parametrize(
    "notice",
    ["participant_left", "track_published"],
    ids=["leaving", "other-event"],
)
async def test_only_a_join_starts_the_recording(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress, notice: str
) -> None:
    stream = await live_stream(db, event)
    await service.apply_room_notice(
        db, room_notice(notice, stream, commentator(stream)), now=NOW, recorder=recorder
    )
    assert fake_egress.requests == []


async def test_a_listener_joining_starts_no_recording(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    stream = await live_stream(db, event)
    notice = room_notice("participant_joined", stream, "listener-1/PA_x")
    await service.apply_room_notice(db, notice, now=NOW, recorder=recorder)
    assert fake_egress.requests == []


async def test_without_a_recorder_a_join_records_nothing(db: AsyncSession, event: Event) -> None:
    stream = await live_stream(db, event)
    notice = room_notice("participant_joined", stream, commentator(stream))
    await service.apply_room_notice(db, notice, now=NOW)
    assert (await reloaded(db, stream)).hls_path is None


async def test_ending_the_stream_stops_its_recording(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    user = stream.commentator.user
    await service.end_stream(db, user, stream.id, now=LATER, recorder=recorder)
    assert fake_egress.calls(STOP) == [{"egress_id": "EG_test1"}]


async def test_a_failed_stop_still_ends_the_stream(
    db: AsyncSession,
    event: Event,
    recorder: Recorder,
    fake_egress: FakeEgress,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    fake_egress.failure = HTTPStatus.SERVICE_UNAVAILABLE
    with caplog.at_level(logging.WARNING, logger=service.__name__):
        ended = await service.end_stream(
            db, stream.commentator.user, stream.id, now=LATER, recorder=recorder
        )
    assert ended.ended_at == LATER
    assert f"stream {stream.id}: recording did not stop" in caplog.text


async def test_ending_a_stream_that_never_recorded_stops_nothing(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    stream = await live_stream(db, event)
    await service.end_stream(db, stream.commentator.user, stream.id, now=LATER, recorder=recorder)
    assert fake_egress.requests == []


async def test_abandoned_streams_stop_their_recordings(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    recorded = await commentator_joins(db, await live_stream(db, event), recorder)
    unrecorded_event = await add_event(db, source_id="402")
    other = await add_commentator(db, "other@example.com", "other_cast")
    await service.go_live(db, other, GoLive(event_id=unrecorded_event.id), now=NOW)
    await db.execute(update(Event).values(status=EventStatus.FINAL))  # both games are over
    await db.commit()
    ended = await service.end_abandoned_streams(db, now=LATER, audio_grace=GRACE, recorder=recorder)
    assert len(ended) == 2
    assert fake_egress.calls(STOP) == [{"egress_id": recorded.recording_id}]


async def test_the_room_closing_leaves_the_recording_to_end_itself(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    """LiveKit ends a room's recording with the room; a stop would only fail."""
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    await service.apply_room_notice(
        db, room_notice("room_finished", stream), now=LATER, recorder=recorder
    )
    assert fake_egress.calls(STOP) == []


async def test_a_listener_gets_the_recordings_playlist(
    db: AsyncSession, event: Event, recorder: Recorder, hls_settings: Settings
) -> None:
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    access = await service.listener_playlist(db, stream.id, hls_settings)
    assert access.url == f"{TEST_HLS_BASE_URL}/{stream.hls_path}/index.m3u8"


async def test_there_is_no_playlist_before_the_recording_starts(
    db: AsyncSession, event: Event, hls_settings: Settings
) -> None:
    stream = await live_stream(db, event)
    with pytest.raises(NotRecordingError):
        await service.listener_playlist(db, stream.id, hls_settings)


async def test_there_is_no_playlist_with_hls_off(
    db: AsyncSession, event: Event, recorder: Recorder, settings: Settings
) -> None:
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    with pytest.raises(NotRecordingError):
        await service.listener_playlist(db, stream.id, settings)


async def test_an_ended_stream_has_no_playlist(
    db: AsyncSession, event: Event, recorder: Recorder, hls_settings: Settings
) -> None:
    stream = await commentator_joins(db, await live_stream(db, event), recorder)
    await service.end_stream(db, stream.commentator.user, stream.id, now=LATER)
    with pytest.raises(StreamEndedError):
        await service.listener_playlist(db, stream.id, hls_settings)


async def test_recording_is_logged_by_stream_id_and_never_its_path(
    db: AsyncSession,
    event: Event,
    recorder: Recorder,
    hls_settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Security: the path is the key to the recording, so it stays out of logs."""
    with caplog.at_level(logging.INFO, logger=service.__name__):
        stream = await commentator_joins(db, await live_stream(db, event), recorder)
        await service.listener_playlist(db, stream.id, hls_settings)
    messages = [r.getMessage() for r in caplog.records if r.name == service.__name__]
    assert messages[-2:] == [
        f"stream {stream.id} recording",
        f"playlist issued for stream {stream.id}",
    ]
    assert stream.hls_path is not None
    assert stream.hls_path not in caplog.text


async def test_a_join_that_loses_the_claim_starts_nothing(
    db: AsyncSession, event: Event, recorder: Recorder, fake_egress: FakeEgress
) -> None:
    """Two joins at once (a reload) both read "not recording"; the database
    claim lets only one start. Here the other join's claim lands first."""
    # Loaded in this session with every column: it reads "not recording".
    stream = await reloaded(db, await live_stream(db, event))
    claimed_elsewhere = (
        update(Stream)
        .where(Stream.id == stream.id)
        .values(hls_path="claimed-by-the-other")
        .execution_options(synchronize_session=False)  # this session still reads None
    )
    await db.execute(claimed_elsewhere)
    await db.commit()
    notice = room_notice("participant_joined", stream, commentator(stream))
    await service.apply_room_notice(db, notice, now=NOW, recorder=recorder)
    assert fake_egress.requests == []
    assert (await reloaded(db, stream)).hls_path == "claimed-by-the-other"
