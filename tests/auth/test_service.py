import logging
from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidTokenError,
    LoginLockedError,
)
from app.auth.models import User
from app.auth.schema import Credentials, Registration, TokenPair
from app.auth.sessions import end_all_sessions
from app.auth.tokens import AccessClaims, create_access_token
from app.common.config import Settings
from tests.conftest import DISPLAY_NAME, EMAIL, PASSWORD

pytestmark = pytest.mark.anyio


def registration(email: str = EMAIL) -> Registration:
    return Registration.model_validate(
        {"email": email, "password": PASSWORD, "display_name": DISPLAY_NAME}
    )


def credentials(password: str = PASSWORD, email: str = EMAIL) -> Credentials:
    return Credentials.model_validate({"email": email, "password": password})


async def register(db: AsyncSession, settings: Settings, email: str = EMAIL) -> TokenPair:
    return await service.register(db, registration(email), settings, now=datetime.now(UTC))


async def log_in(
    db: AsyncSession, cache: Redis, settings: Settings, password: str = PASSWORD
) -> TokenPair:
    return await service.log_in(db, cache, credentials(password), settings, now=datetime.now(UTC))


@pytest.mark.parametrize(
    ("given", "stored"),
    [("fan@example.com", "fan@example.com"), ("  Fan@Example.COM ", "fan@example.com")],
    ids=["already-normal", "mixed-case-and-padding"],
)
def test_emails_are_normalised(given: str, stored: str) -> None:
    assert service.normalise_email(given) == stored


async def test_register_stores_a_hash_not_the_password(
    db: AsyncSession, migrated_settings: Settings
) -> None:
    await register(db, migrated_settings, email="Fan@Example.com")
    user = (await db.execute(select(User))).scalar_one()
    assert user.email == "fan@example.com"
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


async def test_register_twice_is_an_email_taken_error(
    db: AsyncSession, migrated_settings: Settings
) -> None:
    await register(db, migrated_settings)
    with pytest.raises(EmailTakenError):
        await register(db, migrated_settings, email=EMAIL.upper())
    # The session is usable after the failed insert.
    await register(db, migrated_settings, email="other@example.com")


async def test_logs_name_accounts_by_id_never_by_email(
    db: AsyncSession, cache: Redis, migrated_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule 18: no emails or passwords in the logs."""
    with caplog.at_level(logging.INFO, logger="app.auth"):
        await register(db, migrated_settings)
        with pytest.raises(InvalidCredentialsError):
            await log_in(db, cache, migrated_settings, password="wrong password!")
        await log_in(db, cache, migrated_settings)
    assert "registered" in caplog.text
    assert "signed in" in caplog.text
    assert "login failed: wrong password" in caplog.text
    for sensitive in (EMAIL, PASSWORD, "wrong password!"):
        assert sensitive not in caplog.text


async def test_an_unknown_email_counts_towards_the_lockout(
    db: AsyncSession, cache: Redis, migrated_settings: Settings
) -> None:
    """Otherwise the lockout would tell an attacker which emails have accounts."""
    for _ in range(migrated_settings.login_max_failures):
        with pytest.raises(InvalidCredentialsError):
            await log_in(db, cache, migrated_settings)
    with pytest.raises(LoginLockedError):
        await log_in(db, cache, migrated_settings)


async def test_login_upgrades_a_hash_made_with_older_settings(
    db: AsyncSession, cache: Redis, migrated_settings: Settings
) -> None:
    await register(db, migrated_settings)
    user = (await db.execute(select(User))).scalar_one()
    user.password_hash = PasswordHasher(time_cost=1, memory_cost=8 * 1024).hash(PASSWORD)
    await db.commit()
    old_hash = user.password_hash

    await log_in(db, cache, migrated_settings)
    await db.refresh(user)
    assert user.password_hash != old_hash
    assert "m=65536" in user.password_hash


async def test_authenticate_finds_the_token_owner(
    db: AsyncSession, migrated_settings: Settings
) -> None:
    pair = await register(db, migrated_settings)
    user = await service.authenticate(db, pair.access_token, migrated_settings)
    assert user.email == EMAIL


async def test_a_token_stops_working_when_its_sessions_are_ended(
    db: AsyncSession, migrated_settings: Settings
) -> None:
    """Regression for stale access: an unexpired token must not outlive the
    sessions it came from."""
    pair = await register(db, migrated_settings)
    user = await service.authenticate(db, pair.access_token, migrated_settings)
    await end_all_sessions(db, user.id, now=datetime.now(UTC))
    await db.commit()
    db.expunge_all()  # no cached copy of the account answers for the database
    with pytest.raises(InvalidTokenError):
        await service.authenticate(db, pair.access_token, migrated_settings)


async def test_a_token_for_a_deleted_account_is_rejected(
    db: AsyncSession, migrated_settings: Settings
) -> None:
    pair = await register(db, migrated_settings)
    await db.execute(delete(User))
    await db.commit()
    db.expunge_all()
    with pytest.raises(InvalidTokenError):
        await service.authenticate(db, pair.access_token, migrated_settings)


async def test_an_expired_token_is_rejected(db: AsyncSession, migrated_settings: Settings) -> None:
    await register(db, migrated_settings)
    user = (await db.execute(select(User))).scalar_one()
    expired = create_access_token(
        AccessClaims(user_id=user.id, session_version=0),
        secret=migrated_settings.auth_secret.get_secret_value(),
        lifetime=timedelta(minutes=15),
        now=datetime.now(UTC) - timedelta(minutes=16),
    )
    with pytest.raises(InvalidTokenError):
        await service.authenticate(db, expired, migrated_settings)
