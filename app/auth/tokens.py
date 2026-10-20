"""Access tokens (signed JWTs) and refresh tokens (random strings, stored hashed)."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from pydantic import BaseModel, ConfigDict, ValidationError

from app.auth.errors import InvalidTokenError

ALGORITHM = "HS256"
ISSUER = "commentary-sync"
REQUIRED_CLAIMS = ("exp", "iat", "iss", "sub", "ver")
REFRESH_TOKEN_BYTES = 32  # 256 bits: too many to guess, so a fast hash is enough to store it


@dataclass(frozen=True)
class AccessClaims:
    """Who an access token was issued to, and under which session version."""

    user_id: uuid.UUID
    session_version: int


class _Payload(BaseModel):
    """The claims a decoded token must carry, checked like any other input."""

    model_config = ConfigDict(frozen=True)

    sub: uuid.UUID
    ver: int


def create_access_token(
    claims: AccessClaims, *, secret: str, lifetime: timedelta, now: datetime
) -> str:
    payload = {
        "sub": str(claims.user_id),
        "ver": claims.session_version,
        "iss": ISSUER,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def read_access_token(token: str, *, secret: str) -> AccessClaims:
    """The token's claims, if its signature, issuer and expiry all check out.

    Only HS256 is accepted, so a token can't pick its own algorithm ("none",
    or RS256 with the secret used as a public key).
    """
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": list(REQUIRED_CLAIMS)},
        )
        payload = _Payload.model_validate(decoded)
    except (jwt.InvalidTokenError, ValidationError) as error:
        raise InvalidTokenError("access token rejected") from error
    return AccessClaims(user_id=payload.sub, session_version=payload.ver)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
