"""LiveKit Egress: records a stream's room as HLS, for listeners whose TV is
far behind.

WebRTC plays audio the moment it arrives, so it can't be held back to match a
TV 40 s behind the commentator's. Egress joins the room as a hidden recorder
and writes its audio as HLS: short segments and a playlist, each segment
stamped with the wall-clock time it was recorded. A player can sit any
distance behind live and seek within it. Locally Egress writes to a volume the
`hls` service serves; deployed it uploads to S3 behind CloudFront, and only
`hls_output_root` and `hls_base_url` change.

The API is LiveKit's server API: JSON POSTs (Twirp), signed like a room token
but with a `roomRecord` grant. Everything Egress-specific is here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus

import httpx2
import jwt
from fastapi import Request
from pydantic import ValidationError

from app.common.config import Settings
from app.common.schema import FrozenModel
from app.streams.errors import RecorderError
from app.streams.livekit import ALGORITHM
from app.streams.schema import RecordingInfo, RoomRecording, SegmentOutput, StopRecording

EGRESS_SERVICE_PATH = "/twirp/livekit.Egress/"
PLAYLIST_NAME = "index.m3u8"
SEGMENT_PREFIX = "s"
# A server API token is used once, at once.
SERVER_TOKEN_LIFETIME = timedelta(minutes=1)
# Stopping a recording that already finished (412: the room closed) or that
# LiveKit no longer knows (404) leaves it stopped, which is what was asked.
ALREADY_STOPPED = frozenset({HTTPStatus.PRECONDITION_FAILED, HTTPStatus.NOT_FOUND})


@dataclass(frozen=True)
class Recorder:
    """Starts and stops HLS recordings of stream rooms."""

    client: httpx2.AsyncClient  # its base_url is LiveKit's server API
    api_key: str
    api_secret: str
    output_root: str
    segment_seconds: int

    async def start(self, room: str, hls_path: str, *, now: datetime) -> str:
        """Record `room` into `hls_path`; returns the recording's ID."""
        output = SegmentOutput(
            filename_prefix=f"{self.output_root}/{hls_path}/{SEGMENT_PREFIX}",
            playlist_name=PLAYLIST_NAME,
            segment_duration=self.segment_seconds,
        )
        request = RoomRecording(room_name=room, segment_outputs=(output,))
        response = await self._call("StartRoomCompositeEgress", request, now)
        try:
            return RecordingInfo.model_validate_json(response.content).egress_id
        except ValidationError as error:
            raise RecorderError("egress start answered without an egress ID") from error

    async def stop(self, recording_id: str, *, now: datetime) -> None:
        await self._call("StopEgress", StopRecording(egress_id=recording_id), now, ALREADY_STOPPED)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _call(
        self,
        method: str,
        request: FrozenModel,
        now: datetime,
        also_fine: frozenset[HTTPStatus] = frozenset(),
    ) -> httpx2.Response:
        token = jwt.encode(
            {
                "iss": self.api_key,
                "nbf": now,
                "exp": now + SERVER_TOKEN_LIFETIME,
                "video": {"roomRecord": True},
            },
            self.api_secret,
            algorithm=ALGORITHM,
        )
        try:
            response = await self.client.post(
                EGRESS_SERVICE_PATH + method,
                content=request.model_dump_json(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        except httpx2.HTTPError as error:
            raise RecorderError(f"egress {method}: {type(error).__name__}") from error
        if response.is_success or response.status_code in also_fine:
            return response
        raise RecorderError(f"egress {method}: HTTP {response.status_code}")


def playlist_url(hls_base_url: str, hls_path: str) -> str:
    return f"{hls_base_url.rstrip('/')}/{hls_path}/{PLAYLIST_NAME}"


def create_recorder(
    settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
) -> Recorder | None:
    """The recorder the settings describe, or None when HLS is off. Pass
    `transport` to send its requests somewhere other than the network."""
    if settings.livekit_api_url is None:
        return None
    client = httpx2.AsyncClient(
        base_url=str(settings.livekit_api_url),
        timeout=httpx2.Timeout(settings.livekit_api_timeout_seconds),
        transport=transport,
    )
    return Recorder(
        client=client,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret.get_secret_value(),
        output_root=settings.hls_output_root,
        segment_seconds=settings.hls_segment_seconds,
    )


def get_recorder(request: Request) -> Recorder | None:
    """FastAPI dependency: the app's recorder, or None when HLS is off."""
    recorder: Recorder | None = request.app.state.recorder
    return recorder
