"""Request and response shapes for streams."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import Page
from app.common.schema import FrozenModel
from app.streams.models import MAX_RECORDING_ID_LENGTH


class StreamStatus(StrEnum):
    LIVE = "live"
    ENDED = "ended"


class GoLive(FrozenModel):
    event_id: uuid.UUID


class StreamCommentator(FrozenModel):
    """Who is talking: enough for a listener to pick, and to open the profile."""

    handle: str
    display_name: str


class StreamResponse(FrozenModel):
    id: uuid.UUID
    event_id: uuid.UUID
    commentator: StreamCommentator
    status: StreamStatus
    started_at: datetime
    ended_at: datetime | None
    # Accounts listening now (app/streams/audience.py); None when the count
    # is unavailable, and 0 once the stream has ended.
    listeners: int | None


class StreamPage(Page[StreamResponse]):
    """One page of live streams, longest-running first."""


class RoomAccess(FrozenModel):
    """What a client needs to join a stream's audio room: connect to `url`
    with `token` within `expires_in` seconds."""

    url: str
    room: str
    token: str
    expires_in: int


class PlaylistAccess(FrozenModel):
    """Where a listener plays a stream's HLS recording. The URL is the only
    key to it, so it is handed out like a token: to signed-in accounts, never
    cached."""

    url: str


class SyncStatus(StrEnum):
    MATCHED = "matched"
    # The recording wasn't found in the commentator's room audio: their TV
    # may not have reached that moment yet (try again shortly), or the two
    # TVs show different broadcasts.
    NOT_FOUND = "not_found"


class SyncResult(FrozenModel):
    """How far behind the commentator's TV the listener's TV is.

    `delay_seconds` is the delay to play the commentary at: positive when the
    listener's TV is behind, negative when it is ahead (then only pausing the
    TV can line them up).
    """

    status: SyncStatus
    delay_seconds: float | None = None
    peak_ratio: float | None = None  # how clearly the match beat the next best


class RoomEvent(StrEnum):
    """The LiveKit webhook events this API acts on; it acknowledges the rest."""

    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    ROOM_FINISHED = "room_finished"


class LiveKitModel(BaseModel):
    """LiveKit's webhook JSON, which has many fields this API ignores."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class NoticeRoom(LiveKitModel):
    name: str


class NoticeParticipant(LiveKitModel):
    sid: str  # this connection's ID
    identity: str  # who: the identity in the token it joined with


class RoomNotice(LiveKitModel):
    """One LiveKit webhook: what happened, in which room, to whom."""

    event: str  # a RoomEvent, or one this API doesn't act on
    room: NoticeRoom | None = None
    participant: NoticeParticipant | None = None


# LiveKit Egress requests (app/streams/recorder.py), as its server API takes
# them: JSON with protobuf's field names.


class SegmentOutput(FrozenModel):
    """HLS: segments named `<filename_prefix>_00000.ts`, ... and a playlist
    beside them."""

    filename_prefix: str
    playlist_name: str
    segment_duration: int


class RoomRecording(FrozenModel):
    """Record a room's audio mix. A room, not one participant: a participant
    recording ends when the commentator reconnects, a room's carries on."""

    room_name: str
    audio_only: bool = True
    segment_outputs: tuple[SegmentOutput, ...]


class StopRecording(FrozenModel):
    egress_id: str


class RecordingInfo(LiveKitModel):
    """LiveKit's answer to a start: the ID to stop it with."""

    egress_id: str = Field(min_length=1, max_length=MAX_RECORDING_ID_LENGTH)
