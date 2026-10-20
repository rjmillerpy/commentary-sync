"""LiveKit room tokens: the boundary to the open-source media server that
carries commentary audio.

Clients send and receive audio with LiveKit directly; this API only decides
who may join which room, and as what, by signing a token. The format is
LiveKit's (an HS256 JWT with a `video` grant). LiveKit reports back with
webhooks, signed the same way. Everything LiveKit-specific is here and in
recorder.py (its HLS recorder), so a hosted LiveKit or another media server
changes only these two modules.
"""

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import jwt
from pydantic import ValidationError

from app.streams.errors import WebhookPayloadError, WebhookSignatureError
from app.streams.schema import RoomNotice

ALGORITHM = "HS256"
ROOM_PREFIX = "stream-"
PUBLISHER_PREFIX = "commentator-"
MICROPHONE_SOURCE = "microphone"
# The claim a webhook's token carries the body's SHA-256 in (base64).
BODY_HASH_CLAIM = "sha256"
WEBHOOK_REQUIRED_CLAIMS = ("iss", "exp", BODY_HASH_CLAIM)
CLOCK_SKEW = timedelta(seconds=10)


class RoomRole(StrEnum):
    # Sends microphone audio. It may also subscribe: LiveKit's client SDKs
    # wait for the subscriber connection before they count as connected, so a
    # token without it never connects. Listeners can't publish, so there is
    # nothing for a commentator to hear.
    PUBLISHER = "publisher"
    # Hears audio only, and is hidden: nobody in the room sees who listens.
    LISTENER = "listener"


@dataclass(frozen=True)
class RoomGrant:
    """Who may join which room, as what."""

    room: str
    identity: str  # unique in the room; a second join with it replaces the first
    role: RoomRole
    display_name: str | None = None


def room_name(stream_id: uuid.UUID) -> str:
    """One room per stream."""
    return f"{ROOM_PREFIX}{stream_id}"


def publisher_identity(commentator_id: uuid.UUID) -> str:
    """The identity a commentator sends audio as. Stable, so a second
    connection (a reload) replaces the first rather than joining beside it."""
    return f"{PUBLISHER_PREFIX}{commentator_id}"


def stream_id_from_room(room: str) -> uuid.UUID | None:
    """The stream a room belongs to, or None for a room this API didn't name."""
    if not room.startswith(ROOM_PREFIX):
        return None
    try:
        return uuid.UUID(room.removeprefix(ROOM_PREFIX))
    except ValueError:
        return None


def verify_webhook(
    body: bytes, authorization: str | None, *, api_key: str, api_secret: str
) -> RoomNotice:
    """The notice in a LiveKit webhook, if LiveKit sent it.

    LiveKit puts a JWT in the Authorization header (no "Bearer"), signed with
    the API secret, issued by the API key, carrying the body's SHA-256: so the
    body can't be swapped under a captured header. Raises WebhookSignatureError
    for anything else, and WebhookPayloadError for a signed body this can't read.
    """
    if not authorization:
        raise WebhookSignatureError("no Authorization header")
    try:
        claims = jwt.decode(
            authorization,
            api_secret,
            algorithms=[ALGORITHM],
            issuer=api_key,
            leeway=CLOCK_SKEW,
            options={"require": list(WEBHOOK_REQUIRED_CLAIMS)},
        )
    except jwt.InvalidTokenError as error:
        raise WebhookSignatureError(f"bad webhook token: {type(error).__name__}") from error
    body_hash = base64.b64encode(hashlib.sha256(body).digest()).decode()
    if not hmac.compare_digest(str(claims[BODY_HASH_CLAIM]), body_hash):
        raise WebhookSignatureError("webhook body does not match its signature")
    try:
        return RoomNotice.model_validate_json(body)
    except ValidationError as error:
        raise WebhookPayloadError("signed webhook body is not a room notice") from error


def create_room_token(
    grant: RoomGrant, *, api_key: str, api_secret: str, lifetime: timedelta, now: datetime
) -> str:
    is_publisher = grant.role is RoomRole.PUBLISHER
    video: dict[str, object] = {
        "room": grant.room,
        "roomJoin": True,
        "canPublish": is_publisher,
        "canSubscribe": True,
        "canPublishData": False,
        "hidden": not is_publisher,
    }
    if is_publisher:
        video["canPublishSources"] = [MICROPHONE_SOURCE]  # a mic, never a camera or screen
    payload: dict[str, object] = {
        "iss": api_key,
        "sub": grant.identity,
        "nbf": now,
        "exp": now + lifetime,
        "video": video,
    }
    if grant.display_name is not None:
        payload["name"] = grant.display_name
    return jwt.encode(payload, api_secret, algorithm=ALGORITHM)
