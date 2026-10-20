"""Streams fixtures: real event rows and a commentator, made the way the app
makes them, and LiveKit's server API, replaced at the network."""

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import httpx2
import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.commentators import service as commentators
from app.commentators.schema import CommentatorSignup
from app.common.config import Settings
from app.events.models import Event
from app.events.schema import EventStatus, League
from app.streams.recorder import Recorder, create_recorder
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
