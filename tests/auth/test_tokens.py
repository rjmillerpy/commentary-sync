import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.errors import InvalidTokenError
from app.auth.tokens import (
    ALGORITHM,
    ISSUER,
    AccessClaims,
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    read_access_token,
)

# 64 bytes, so the HS512 case below signs without a short-key warning.
SECRET = "test-only-signing-secret-" + "x" * 39
CLAIMS = AccessClaims(user_id=uuid.UUID("0b0c4e0e-6a52-4a5e-9d55-5b0a3c1d2e3f"), session_version=3)
LIFETIME = timedelta(minutes=15)


def issue(now: datetime | None = None, secret: str = SECRET) -> str:
    return create_access_token(
        CLAIMS, secret=secret, lifetime=LIFETIME, now=now or datetime.now(UTC)
    )


def signed(payload: dict[str, object], algorithm: str = ALGORITHM) -> str:
    return jwt.encode(payload, SECRET, algorithm=algorithm)


def valid_payload(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(CLAIMS.user_id),
        "ver": CLAIMS.session_version,
        "iss": ISSUER,
        "iat": now,
        "exp": now + LIFETIME,
    }
    return {**payload, **overrides}


def test_a_token_reads_back_as_its_claims() -> None:
    assert read_access_token(issue(), secret=SECRET) == CLAIMS


def test_a_token_is_good_until_it_expires() -> None:
    almost_expired = datetime.now(UTC) - LIFETIME + timedelta(seconds=30)
    assert read_access_token(issue(now=almost_expired), secret=SECRET) == CLAIMS


def without(claim: str) -> dict[str, object]:
    return {key: value for key, value in valid_payload().items() if key != claim}


@pytest.mark.parametrize(
    "token",
    [
        issue(now=datetime.now(UTC) - LIFETIME - timedelta(seconds=1)),
        issue(secret="another-secret-that-is-32-chars-long"),
        signed(valid_payload(iss="someone-else")),
        signed(valid_payload(sub="not-a-uuid")),
        signed(valid_payload(ver="three")),
        signed(without("exp")),
        signed(without("ver")),
        signed(without("sub")),
        jwt.encode(valid_payload(), key=None, algorithm="none"),
        signed(valid_payload(), algorithm="HS512"),
        "not.a.token",
        "",
    ],
    ids=[
        "expired",
        "other-secret",
        "other-issuer",
        "subject-not-a-uuid",
        "version-not-a-number",
        "no-expiry",
        "no-version",
        "no-subject",
        "alg-none",
        "other-algorithm",
        "garbage",
        "empty",
    ],
)
def test_bad_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        read_access_token(token, secret=SECRET)


def test_a_tampered_token_is_rejected() -> None:
    header, _, signature = issue().split(".")
    forged_body = jwt.utils.base64url_encode(b'{"sub":"x","ver":0}').decode()
    with pytest.raises(InvalidTokenError):
        read_access_token(f"{header}.{forged_body}.{signature}", secret=SECRET)


def test_refresh_tokens_are_random_and_long() -> None:
    tokens = {new_refresh_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)  # 32 bytes, base64url


def test_a_refresh_token_hash_is_stable_and_hides_the_token() -> None:
    token = new_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64
    assert token not in hash_refresh_token(token)
    assert hash_refresh_token(token) != hash_refresh_token(new_refresh_token())
