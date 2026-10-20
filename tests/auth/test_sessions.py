from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import sessions
from app.auth.errors import InvalidTokenError
from app.auth.models import RefreshToken, User
from app.auth.tokens import hash_refresh_token, read_access_token
from app.common.config import Settings
from tests.auth.conftest import NOW

pytestmark = pytest.mark.anyio


@pytest.fixture
async def user(db: AsyncSession) -> User:
    account = User(email="fan@example.com", display_name="Fan", password_hash="$argon2id$x")
    db.add(account)
    await db.commit()
    return account


async def start(db: AsyncSession, user: User, settings: Settings, *, days_ago: int = 0) -> str:
    pair = await sessions.start_session(db, user, settings, now=NOW - timedelta(days=days_ago))
    await db.commit()
    return pair.refresh_token


async def token_rows(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(RefreshToken))).scalar_one()


async def test_only_a_hash_of_the_refresh_token_is_stored(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    token = await start(db, user, migrated_settings)
    stored = (await db.execute(select(RefreshToken))).scalar_one()
    assert stored.token_hash == hash_refresh_token(token)
    assert stored.expires_at.replace(tzinfo=UTC) == NOW + timedelta(days=30)


async def test_the_access_token_carries_the_session_version(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    # Issued now, not at NOW: a token from the future isn't valid yet.
    pair = await sessions.start_session(db, user, migrated_settings, now=datetime.now(UTC))
    claims = read_access_token(
        pair.access_token, secret=migrated_settings.auth_secret.get_secret_value()
    )
    assert claims.user_id == user.id
    assert claims.session_version == user.session_version


async def test_starting_a_session_clears_expired_ones(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    """Rule 11: an account's token rows stay bounded."""
    await start(db, user, migrated_settings, days_ago=31)  # expired a day ago
    await start(db, user, migrated_settings, days_ago=29)  # still good tomorrow
    assert await token_rows(db) == 2
    await start(db, user, migrated_settings)
    assert await token_rows(db) == 2


async def test_rotating_spends_the_token(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    token = await start(db, user, migrated_settings)
    pair = await sessions.rotate_session(db, token, migrated_settings, now=NOW)
    assert pair.refresh_token != token
    spent = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    assert spent is not None
    assert spent.revoked_at is not None  # kept, to recognise reuse


async def test_an_expired_token_is_rejected_without_ending_other_sessions(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    expired = await start(db, user, migrated_settings, days_ago=31)
    current = await start(db, user, migrated_settings)
    with pytest.raises(InvalidTokenError):
        await sessions.rotate_session(db, expired, migrated_settings, now=NOW)
    assert await sessions.rotate_session(db, current, migrated_settings, now=NOW)


async def test_reuse_ends_every_session_and_raises_the_version(
    db: AsyncSession, user: User, migrated_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    token = await start(db, user, migrated_settings)
    await sessions.rotate_session(db, token, migrated_settings, now=NOW)
    with pytest.raises(InvalidTokenError):
        await sessions.rotate_session(db, token, migrated_settings, now=NOW)

    await db.refresh(user)
    assert user.session_version == 1
    live = select(func.count()).where(RefreshToken.revoked_at.is_(None))
    assert (await db.execute(live)).scalar_one() == 0
    assert f"ending every session of user {user.id}" in caplog.text


async def test_ending_a_session_deletes_it(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    token = await start(db, user, migrated_settings)
    await sessions.end_session(db, token)
    assert await token_rows(db) == 0
    await sessions.end_session(db, token)  # twice is fine


async def test_ending_all_sessions_leaves_other_accounts_alone(
    db: AsyncSession, user: User, migrated_settings: Settings
) -> None:
    other = User(email="other@example.com", display_name="Other", password_hash="$argon2id$x")
    db.add(other)
    await db.commit()
    other_token = await start(db, other, migrated_settings)
    await start(db, user, migrated_settings)

    await sessions.end_all_sessions(db, user.id, now=NOW)
    await db.commit()
    await db.refresh(other)
    assert other.session_version == 0
    assert await sessions.rotate_session(db, other_token, migrated_settings, now=NOW)
