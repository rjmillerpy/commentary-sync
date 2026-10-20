import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken, User

pytestmark = pytest.mark.anyio

EXPIRES = datetime(2026, 11, 18, tzinfo=UTC)


def new_user(email: str = "fan@example.com") -> User:
    return User(email=email, display_name="Fan", password_hash="$argon2id$stand-in")


async def test_a_user_round_trips_with_database_defaults(db: AsyncSession) -> None:
    db.add(new_user())
    await db.commit()
    db.expunge_all()

    stored = (await db.execute(select(User))).scalar_one()
    assert isinstance(stored.id, uuid.UUID)
    assert stored.session_version == 0
    assert stored.created_at is not None
    assert stored.updated_at is not None


async def test_one_account_per_email(db: AsyncSession) -> None:
    db.add_all([new_user(), new_user()])
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_a_refresh_token_belongs_to_a_user(db: AsyncSession) -> None:
    user = new_user()
    db.add(user)
    await db.flush()
    db.add(RefreshToken(user_id=user.id, token_hash="a" * 64, expires_at=EXPIRES))
    await db.commit()
    db.expunge_all()

    stored = (await db.execute(select(RefreshToken))).scalar_one()
    assert stored.user_id == user.id
    assert stored.revoked_at is None
    assert stored.expires_at.replace(tzinfo=UTC) == EXPIRES


async def test_token_hashes_are_unique(db: AsyncSession) -> None:
    user = new_user()
    db.add(user)
    await db.flush()
    later = EXPIRES + timedelta(days=1)
    db.add_all(
        [
            RefreshToken(user_id=user.id, token_hash="a" * 64, expires_at=EXPIRES),
            RefreshToken(user_id=user.id, token_hash="a" * 64, expires_at=later),
        ]
    )
    with pytest.raises(IntegrityError):
        await db.commit()
