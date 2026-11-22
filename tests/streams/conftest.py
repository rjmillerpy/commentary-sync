"""Streams fixtures: real event rows and a commentator, made the way the app
makes them, and LiveKit's server API, replaced at the network."""

import base64
import hashlib
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import av
import httpx2
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.commentators import service as commentators
from app.commentators.schema import CommentatorSignup
from app.common.config import Settings, get_settings
from app.events.models import Event
from app.events.schema import EventStatus, League
from app.simulation.broadcast import SOURCE_SAMPLE_RATE
from app.streams.hls_audio import HlsReader, create_hls_reader
from app.streams.recorder import Recorder, create_recorder, get_recorder
from app.sync.audio import encode_aac
from app.sync.schema import Samples
from tests.conftest import TEST_LIVEKIT_API_KEY, TEST_LIVEKIT_API_SECRET, Account, bearer

KICKOFF = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 18, 17, 5, tzinfo=UTC)
WEBHOOK_LIFETIME = timedelta(minutes=5)  # what livekit-server signs them for
TEST_LIVEKIT_API_URL = "http://livekit.test:7880"
TEST_HLS_BASE_URL = "https://hls.example.com/live"
START = "StartRoomCompositeEgress"
STOP = "StopEgress"


async def add_event(
    db: AsyncSession, status: EventStatus = EventStatus.LIVE, source_id: str = "401"
) -> Event:
    event = Event(
        source="espn",
        source_event_id=source_id,
        league=League.NFL,
        title="Houston Texans at Jacksonville Jaguars",
        home_team="Jacksonville Jaguars",
        away_team="Houston Texans",
        starts_at=KICKOFF,
        status=status,
        networks=["CBS"],
    )
    db.add(event)
    await db.commit()
    return event


async def add_user(db: AsyncSession, email: str = "fan@example.com", name: str = "Fan") -> User:
    user = User(email=email, display_name=name, password_hash="$argon2id$stand-in")
    db.add(user)
    await db.commit()
    return user


async def add_commentator(
    db: AsyncSession, email: str = "fan@example.com", handle: str = "fan_cast"
) -> User:
    """An account with a commentator profile; returns the account."""
    user = await add_user(db, email)
    await commentators.become_commentator(db, user, CommentatorSignup(handle=handle))
    return user


@pytest.fixture
async def event(db: AsyncSession) -> Event:
    return await add_event(db)


def sign_webhook(
    body: bytes,
    *,
    secret: str = TEST_LIVEKIT_API_SECRET,
    issuer: str = TEST_LIVEKIT_API_KEY,
    lifetime: timedelta = WEBHOOK_LIFETIME,
) -> str:
    """The Authorization header LiveKit sends with `body` (livekit-server's
    webhook notifier): an HS256 JWT carrying the body's SHA-256 in base64."""
    now = datetime.now(UTC)
    claims = {
        "iss": issuer,
        "nbf": now,
        "exp": now + lifetime,
        "sha256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def notice_body(event: str, stream_id: uuid.UUID, participant: str | None = None) -> bytes:
    """A LiveKit webhook body for `event` in a stream's room; `participant`
    is "<identity>/<sid>". Extra fields, as LiveKit sends, are ignored."""
    notice: dict[str, object] = {
        "event": event,
        "room": {"sid": "RM_test", "name": f"stream-{stream_id}", "numParticipants": 1},
        "id": "EV_test",
        "createdAt": "1792342800",
    }
    if participant is not None:
        identity, sid = participant.split("/")
        notice["participant"] = {"sid": sid, "identity": identity, "state": "ACTIVE"}
    return json.dumps(notice).encode()


@dataclass
class FakeEgress:
    """LiveKit's server API for Egress, as livekit-server answers: a start gets
    a new egress ID, a stop is acknowledged. `failure` makes every call answer
    with that status instead, as LiveKit's errors look (Twirp JSON)."""

    requests: list[httpx2.Request] = field(default_factory=list)
    failure: HTTPStatus | None = None

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.failure is not None:
            return httpx2.Response(self.failure, json={"code": "unavailable", "msg": "no"})
        body = json.loads(request.content)
        if request.url.path.endswith(START):
            number = len(self.calls(START))  # this one included: EG_test1 first
            info = {"egress_id": f"EG_test{number}", "room_name": body["room_name"]}
            return httpx2.Response(HTTPStatus.OK, json={**info, "status": "EGRESS_STARTING"})
        return httpx2.Response(HTTPStatus.OK, json={**body, "status": "EGRESS_ENDING"})

    def calls(self, method: str) -> list[dict[str, object]]:
        """The bodies of the calls to one method, in order."""
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path.endswith(f"/{method}")
        ]


@pytest.fixture
def fake_egress() -> FakeEgress:
    return FakeEgress()


@pytest.fixture
def hls_settings(settings: Settings) -> Settings:
    """`settings` with HLS on."""
    return settings.model_copy(
        update={
            "livekit_api_url": HttpUrl(TEST_LIVEKIT_API_URL),
            "hls_base_url": HttpUrl(TEST_HLS_BASE_URL),
        }
    )


@pytest.fixture
def recorder(hls_settings: Settings, fake_egress: FakeEgress) -> Recorder:
    """The real recorder, its requests answered by FakeEgress."""
    built = create_recorder(hls_settings, httpx2.MockTransport(fake_egress.handle))
    assert built is not None
    return built


def webhook(api: TestClient, body: bytes, authorization: str | None = None) -> httpx2.Response:
    headers = {"Content-Type": "application/webhook+json"}  # what LiveKit sends
    if authorization is not None:
        headers["Authorization"] = authorization
    return api.post("/webhooks/livekit", content=body, headers=headers)


def make_commentator(api: TestClient, account: Account, handle: str = "fan_cast") -> None:
    response = api.post(
        "/commentators", json={"handle": handle}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 201, response.text


def go_live(api: TestClient, account: Account, event: Event) -> dict[str, object]:
    response = api.post(
        "/streams", json={"event_id": str(event.id)}, headers=bearer(account.tokens.access_token)
    )
    assert response.status_code == 201, response.text
    stream: dict[str, object] = response.json()
    return stream


def commentator_connects(api: TestClient, stream: dict[str, object], account: Account) -> None:
    """What LiveKit sends when the studio joins the stream's room."""
    me = api.get("/commentators/me", headers=bearer(account.tokens.access_token)).json()
    identity = f"commentator-{me['id']}/PA_one"
    body = notice_body("participant_joined", uuid.UUID(str(stream["id"])), identity)
    assert webhook(api, body, sign_webhook(body)).status_code == 204


def send_reference(
    api: TestClient, account: Account, stream_id: object, pcm: bytes, at: float
) -> httpx2.Response:
    return api.post(
        f"/streams/{stream_id}/reference",
        params={"captured_at": at},
        content=pcm,
        headers={**bearer(account.tokens.access_token), "Content-Type": "application/octet-stream"},
    )


def send_features(
    api: TestClient, account: Account, stream_id: object, features: bytes, at: float
) -> httpx2.Response:
    return api.post(
        f"/streams/{stream_id}/sync",
        params={"captured_at": at},
        content=features,
        headers={**bearer(account.tokens.access_token), "Content-Type": "application/octet-stream"},
    )


@pytest.fixture
def hls_api(
    api: TestClient, app: FastAPI, hls_settings: Settings, recorder: Recorder
) -> TestClient:
    """The API with HLS on, its recorder talking to FakeEgress."""
    app.dependency_overrides[get_settings] = lambda: hls_settings
    app.dependency_overrides[get_recorder] = lambda: recorder
    return api


HLS_SEGMENT_SECONDS = 2
HLS_BIT_RATE = 48_000
AAC_FRAME_SAMPLES = 1024


@dataclass
class FakeHls:
    """An HLS server (the `hls` service, or CloudFront), in memory: `publish`
    writes a recording as Egress would, 2 s MPEG-TS segments of AAC and a
    playlist stamped with each segment's recording time."""

    files: dict[str, bytes] = field(default_factory=dict)

    def publish(self, hls_path: str, samples: Samples, *, starts_at: float) -> None:
        """`samples` at the source rate, recorded from `starts_at` (epoch seconds).
        Like Egress, one continuous encoder: the AAC is cut into segments
        without re-encoding, so the timeline stays exact."""
        lines = ["#EXTM3U", "#EXT-X-VERSION:3", f"#EXT-X-TARGETDURATION:{HLS_SEGMENT_SECONDS}"]
        for number, (offset, seconds, body) in enumerate(_segments(samples)):
            name = f"s{number:05d}.ts"
            self.files[f"/{hls_path}/{name}"] = body
            recorded = datetime.fromtimestamp(starts_at + offset, UTC).isoformat(
                timespec="milliseconds"
            )
            lines += [f"#EXT-X-PROGRAM-DATE-TIME:{recorded}", f"#EXTINF:{seconds:.3f},", name]
        self.files[f"/{hls_path}/index.m3u8"] = "\n".join(lines).encode()

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        # Files are kept by their path under hls_base_url, whatever its own path is.
        base = httpx2.URL(TEST_HLS_BASE_URL).path.rstrip("/")
        body = self.files.get(request.url.path.removeprefix(base))
        if body is None:
            return httpx2.Response(HTTPStatus.NOT_FOUND)
        return httpx2.Response(HTTPStatus.OK, content=body)


def _segments(samples: Samples) -> list[tuple[float, float, bytes]]:
    """(start, length, MPEG-TS bytes) of each HLS segment of one AAC encoding."""
    whole = io.BytesIO()
    encode_aac(samples, SOURCE_SAMPLE_RATE, whole, bit_rate=HLS_BIT_RATE, container_format="adts")
    whole.seek(0)
    frame_seconds = AAC_FRAME_SAMPLES / SOURCE_SAMPLE_RATE
    segments = []
    with av.open(whole, "r", format="adts") as source:
        template = source.streams.audio[0]
        packets = [packet for packet in source.demux(template) if packet.size > 0]
        groups: dict[int, list[int]] = {}
        for index in range(len(packets)):
            groups.setdefault(int(index * frame_seconds // HLS_SEGMENT_SECONDS), []).append(index)
        first_index = 0
        for indexes in groups.values():
            body = _mpegts(template, [packets[index] for index in indexes])
            segments.append((first_index * frame_seconds, len(indexes) * frame_seconds, body))
            first_index += len(indexes)
    return segments


def _mpegts(template: av.AudioStream, packets: list[av.Packet]) -> bytes:  # type: ignore[type-arg]
    """`packets` muxed, not re-encoded, into an MPEG-TS file."""
    body = io.BytesIO()
    with av.open(body, "w", format="mpegts") as target:
        stream = target.add_stream_from_template(template)
        for packet in packets:
            packet.stream = stream
            target.mux(packet)
    return body.getvalue()


@pytest.fixture
def fake_hls() -> FakeHls:
    return FakeHls()


@pytest.fixture
def hls_reader(hls_settings: Settings, fake_hls: FakeHls) -> HlsReader:
    """The real reader, its requests answered by FakeHls."""
    built = create_hls_reader(hls_settings, httpx2.MockTransport(fake_hls.handle))
    assert built is not None
    return built
