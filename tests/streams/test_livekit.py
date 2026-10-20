import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.streams.errors import WebhookPayloadError, WebhookSignatureError
from app.streams.livekit import (
    RoomGrant,
    RoomRole,
    create_room_token,
    publisher_identity,
    room_name,
    stream_id_from_room,
    verify_webhook,
)
from app.streams.schema import NoticeParticipant, NoticeRoom, RoomNotice
from tests.streams.conftest import notice_body, sign_webhook

API_KEY = "test-livekit-key"
API_SECRET = "test-only-livekit-secret-at-least-32-chars"
NOW = datetime(2026, 10, 18, 17, 0, tzinfo=UTC)
LIFETIME = timedelta(minutes=10)


def signed(grant: RoomGrant) -> dict[str, object]:
    token = create_room_token(
        grant, api_key=API_KEY, api_secret=API_SECRET, lifetime=LIFETIME, now=NOW
    )
    # LiveKit verifies exactly this: HS256 with the secret, issued by the key.
    claims: dict[str, object] = jwt.decode(
        token, API_SECRET, algorithms=["HS256"], options={"verify_exp": False, "verify_nbf": False}
    )
    return claims


def test_one_room_per_stream() -> None:
    stream_id = uuid.uuid4()
    assert room_name(stream_id) == f"stream-{stream_id}"


def test_a_publisher_can_send_microphone_audio_and_nothing_else() -> None:
    claims = signed(RoomGrant("stream-1", "commentator-1", RoomRole.PUBLISHER, "fan_cast"))
    assert (claims["iss"], claims["sub"], claims["name"]) == (API_KEY, "commentator-1", "fan_cast")
    assert claims["video"] == {
        "room": "stream-1",
        "roomJoin": True,
        "canPublish": True,
        "canPublishSources": ["microphone"],
        "canSubscribe": True,
        "canPublishData": False,
        "hidden": False,
    }


def test_regression_a_publisher_token_lets_the_client_finish_connecting() -> None:
    """LiveKit's SDKs wait for the subscriber connection; with canSubscribe
    false, the commentator's client timed out joining (found 2026-10-16
    against the real server)."""
    claims = signed(RoomGrant("stream-1", "commentator-1", RoomRole.PUBLISHER))
    assert claims["video"]["canSubscribe"] is True  # type: ignore[index]


def test_a_listener_can_only_hear_and_is_hidden() -> None:
    claims = signed(RoomGrant("stream-1", "listener-1", RoomRole.LISTENER))
    assert "name" not in claims
    assert claims["video"] == {
        "room": "stream-1",
        "roomJoin": True,
        "canPublish": False,
        "canSubscribe": True,
        "canPublishData": False,
        "hidden": True,
    }


def test_the_token_is_valid_from_now_for_its_lifetime() -> None:
    claims = signed(RoomGrant("stream-1", "listener-1", RoomRole.LISTENER))
    assert claims["nbf"] == int(NOW.timestamp())
    assert claims["exp"] == int((NOW + LIFETIME).timestamp())


def test_only_the_shared_secret_verifies_it() -> None:
    token = create_room_token(
        RoomGrant("stream-1", "listener-1", RoomRole.LISTENER),
        api_key=API_KEY,
        api_secret=API_SECRET,
        lifetime=LIFETIME,
        now=datetime.now(UTC),
    )
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "another-secret-of-at-least-32-characters", algorithms=["HS256"])


def test_a_room_name_leads_back_to_its_stream() -> None:
    stream_id = uuid.uuid4()
    assert stream_id_from_room(room_name(stream_id)) == stream_id


@pytest.mark.parametrize(
    "room", ["lobby", "stream-", "stream-not-a-uuid"], ids=["foreign", "empty-id", "bad-id"]
)
def test_rooms_this_api_didnt_name_have_no_stream(room: str) -> None:
    assert stream_id_from_room(room) is None


def test_a_publisher_identity_is_stable_per_commentator() -> None:
    commentator_id = uuid.uuid4()
    assert publisher_identity(commentator_id) == f"commentator-{commentator_id}"
    assert publisher_identity(commentator_id) == publisher_identity(commentator_id)


def verify(body: bytes, authorization: str | None) -> RoomNotice:
    return verify_webhook(body, authorization, api_key=API_KEY, api_secret=API_SECRET)


def test_a_signed_webhook_is_read() -> None:
    stream_id = uuid.uuid4()
    body = notice_body("participant_left", stream_id, "commentator-1/PA_abc")
    assert verify(body, sign_webhook(body)) == RoomNotice(
        event="participant_left",
        room=NoticeRoom(name=f"stream-{stream_id}"),
        participant=NoticeParticipant(sid="PA_abc", identity="commentator-1"),
    )


def test_a_notice_without_a_participant_is_read() -> None:
    body = notice_body("room_finished", uuid.uuid4())
    assert verify(body, sign_webhook(body)).participant is None


@pytest.mark.parametrize("header", [None, ""], ids=["missing", "empty"])
def test_an_unsigned_webhook_is_rejected(header: str | None) -> None:
    with pytest.raises(WebhookSignatureError, match="no Authorization header"):
        verify(notice_body("room_finished", uuid.uuid4()), header)


@pytest.mark.parametrize(
    "signing",
    [
        {"secret": "someone-elses-secret-also-32-characters-long"},
        {"issuer": "someone-elses-key"},
        {"lifetime": timedelta(minutes=-5)},
    ],
    ids=["wrong-secret", "wrong-issuer", "expired"],
)
def test_a_webhook_not_signed_by_this_livekit_is_rejected(signing: dict[str, object]) -> None:
    body = notice_body("room_finished", uuid.uuid4())
    with pytest.raises(WebhookSignatureError, match="bad webhook token"):
        verify(body, sign_webhook(body, **signing))  # type: ignore[arg-type]


def test_a_signature_cant_be_moved_to_another_body() -> None:
    signed_body = notice_body("participant_joined", uuid.uuid4(), "commentator-1/PA_abc")
    other_body = notice_body("room_finished", uuid.uuid4())
    with pytest.raises(WebhookSignatureError, match="does not match"):
        verify(other_body, sign_webhook(signed_body))


def test_a_token_without_a_body_hash_is_rejected() -> None:
    token = create_room_token(
        RoomGrant(room="stream-x", identity="x", role=RoomRole.LISTENER),
        api_key=API_KEY,
        api_secret=API_SECRET,
        lifetime=LIFETIME,
        now=datetime.now(UTC),
    )
    with pytest.raises(WebhookSignatureError, match="MissingRequiredClaimError"):
        verify(notice_body("room_finished", uuid.uuid4()), token)


@pytest.mark.parametrize(
    "body", [b"not json", b'{"room": {"name": "stream-x"}}'], ids=["not-json", "no-event"]
)
def test_a_signed_body_that_isnt_a_notice_is_a_payload_error(body: bytes) -> None:
    with pytest.raises(WebhookPayloadError):
        verify(body, sign_webhook(body))
