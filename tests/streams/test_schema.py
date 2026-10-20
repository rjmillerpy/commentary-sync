import uuid

import pytest
from pydantic import ValidationError

from app.streams.schema import (
    GoLive,
    RecordingInfo,
    RoomRecording,
    SegmentOutput,
    StreamStatus,
)


def test_go_live_takes_an_event_id() -> None:
    event_id = uuid.uuid4()
    assert GoLive.model_validate({"event_id": str(event_id)}).event_id == event_id


@pytest.mark.parametrize("body", [{}, {"event_id": "not-a-uuid"}], ids=["missing", "malformed"])
def test_go_live_rejects_a_bad_event_id(body: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        GoLive.model_validate(body)


def test_statuses_are_live_and_ended() -> None:
    assert {status.value for status in StreamStatus} == {"live", "ended"}


def test_a_room_recording_is_sent_with_livekits_field_names() -> None:
    output = SegmentOutput(
        filename_prefix="/hls/x/s", playlist_name="index.m3u8", segment_duration=2
    )
    recording = RoomRecording(room_name="stream-1", segment_outputs=(output,))
    assert recording.model_dump() == {
        "room_name": "stream-1",
        "audio_only": True,
        "segment_outputs": (
            {"filename_prefix": "/hls/x/s", "playlist_name": "index.m3u8", "segment_duration": 2},
        ),
    }


def test_recording_info_reads_the_id_and_ignores_the_rest() -> None:
    body = '{"egress_id": "EG_abc", "room_name": "stream-1", "status": "EGRESS_STARTING"}'
    assert RecordingInfo.model_validate_json(body).egress_id == "EG_abc"


@pytest.mark.parametrize(
    "body",
    ["{}", '{"egress_id": ""}', '{"egress_id": "' + "E" * 65 + '"}'],
    ids=["missing", "empty", "too-long"],
)
def test_recording_info_needs_an_id_that_fits_the_column(body: str) -> None:
    with pytest.raises(ValidationError):
        RecordingInfo.model_validate_json(body)
