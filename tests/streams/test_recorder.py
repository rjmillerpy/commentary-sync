from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import httpx2
import jwt
import pytest
from fastapi.testclient import TestClient

from app.common.config import Settings
from app.streams.errors import RecorderError
from app.streams.recorder import Recorder, create_recorder, playlist_url
from tests.conftest import TEST_LIVEKIT_API_KEY, TEST_LIVEKIT_API_SECRET
from tests.streams.conftest import START, STOP, TEST_LIVEKIT_API_URL, FakeEgress

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
ROOM = "stream-6f1c"
HLS_PATH = "Zm9yLXRoZS10ZXN0LW9ubHk"


async def test_a_recording_writes_hls_segments_of_the_room_audio(
    recorder: Recorder, fake_egress: FakeEgress
) -> None:
    assert await recorder.start(ROOM, HLS_PATH, now=NOW) == "EG_test1"
    assert fake_egress.calls(START) == [
        {
            "room_name": ROOM,
            "audio_only": True,
            "segment_outputs": [
                {
                    "filename_prefix": f"/hls/{HLS_PATH}/s",
                    "playlist_name": "index.m3u8",
                    "segment_duration": 2,
                }
            ],
        }
    ]
    assert (
        str(fake_egress.requests[0].url) == f"{TEST_LIVEKIT_API_URL}/twirp/livekit.Egress/{START}"
    )


async def test_calls_are_signed_for_recording_only_and_expire_in_a_minute(
    recorder: Recorder, fake_egress: FakeEgress
) -> None:
    """Security: the token can start or stop a recording, and can't join a room."""
    await recorder.start(ROOM, HLS_PATH, now=NOW)
    scheme, token = fake_egress.requests[0].headers["Authorization"].split(" ")
    claims = jwt.decode(
        token,
        TEST_LIVEKIT_API_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_nbf": False},
    )
    assert scheme == "Bearer"
    assert claims["iss"] == TEST_LIVEKIT_API_KEY
    assert claims["video"] == {"roomRecord": True}
    assert claims["exp"] - claims["nbf"] == timedelta(minutes=1).total_seconds()


async def test_stopping_names_the_recording(recorder: Recorder, fake_egress: FakeEgress) -> None:
    await recorder.stop("EG_abc", now=NOW)
    assert fake_egress.calls(STOP) == [{"egress_id": "EG_abc"}]


@pytest.mark.parametrize(
    "status",
    [HTTPStatus.PRECONDITION_FAILED, HTTPStatus.NOT_FOUND],
    ids=["already-finished", "unknown-to-livekit"],
)
async def test_stopping_a_recording_that_is_already_over_is_fine(
    recorder: Recorder, fake_egress: FakeEgress, status: HTTPStatus
) -> None:
    fake_egress.failure = status
    await recorder.stop("EG_abc", now=NOW)


@pytest.mark.parametrize(
    "status",
    [HTTPStatus.UNAUTHORIZED, HTTPStatus.INTERNAL_SERVER_ERROR, HTTPStatus.SERVICE_UNAVAILABLE],
    ids=["refused", "broken", "unavailable"],
)
async def test_livekit_saying_no_is_a_recorder_error(
    recorder: Recorder, fake_egress: FakeEgress, status: HTTPStatus
) -> None:
    fake_egress.failure = status
    with pytest.raises(RecorderError, match=f"HTTP {status.value}"):
        await recorder.start(ROOM, HLS_PATH, now=NOW)
    with pytest.raises(RecorderError):
        await recorder.stop("EG_abc", now=NOW)


async def test_a_start_answered_without_an_id_is_a_recorder_error(hls_settings: Settings) -> None:
    transport = httpx2.MockTransport(lambda _: httpx2.Response(HTTPStatus.OK, json={}))
    recorder = create_recorder(hls_settings, transport)
    assert recorder is not None
    with pytest.raises(RecorderError, match="without an egress ID"):
        await recorder.start(ROOM, HLS_PATH, now=NOW)


async def test_livekit_out_of_reach_is_a_recorder_error(hls_settings: Settings) -> None:
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    recorder = create_recorder(hls_settings, httpx2.MockTransport(unreachable))
    assert recorder is not None
    with pytest.raises(RecorderError, match="ConnectError"):
        await recorder.start(ROOM, HLS_PATH, now=NOW)


async def test_closing_the_recorder_closes_its_client(recorder: Recorder) -> None:
    await recorder.aclose()
    assert recorder.client.is_closed


def test_there_is_no_recorder_when_hls_is_off(settings: Settings) -> None:
    assert create_recorder(settings) is None


def test_the_recorder_follows_the_settings(hls_settings: Settings) -> None:
    custom = hls_settings.model_copy(update={"hls_output_root": "live", "hls_segment_seconds": 4})
    recorder = create_recorder(custom)
    assert recorder is not None
    assert (recorder.output_root, recorder.segment_seconds) == ("live", 4)
    assert str(recorder.client.base_url) == f"{TEST_LIVEKIT_API_URL}/"


@pytest.mark.parametrize(
    "base", ["https://hls.example.com/live", "https://hls.example.com/live/"], ids=["bare", "slash"]
)
def test_playlist_url_is_the_index_in_the_recording_directory(base: str) -> None:
    assert playlist_url(base, HLS_PATH) == f"https://hls.example.com/live/{HLS_PATH}/index.m3u8"


def test_the_app_has_no_recorder_when_hls_is_off(client: TestClient) -> None:
    assert client.app.state.recorder is None  # type: ignore[attr-defined]
