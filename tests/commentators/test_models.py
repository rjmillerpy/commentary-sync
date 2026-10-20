import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.commentators.models import Commentator

pytestmark = pytest.mark.anyio


async def new_user(db: AsyncSession, email: str = "fan@example.com") -> User:
    user = User(email=email, display_name="Fan", password_hash="$argon2id$stand-in")
    db.add(user)
    await db.flush()
    return user


async def test_a_commentator_round_trips_with_database_defaults(db: AsyncSession) -> None:
    user = await new_user(db)
    commentator = Commentator(user_id=user.id, handle="fan_cast")
    db.add(commentator)
    await db.commit()
    # eager_defaults: the server-made timestamps are already loaded, no extra query.
    assert commentator.created_at is not None
    db.expunge_all()

    stored = (await db.execute(select(Commentator))).scalar_one()
    assert isinstance(stored.id, uuid.UUID)
    assert (stored.user_id, stored.handle, stored.bio) == (user.id, "fan_cast", "")


async def test_one_profile_per_account(db: AsyncSession) -> None:
    user = await new_user(db)
    db.add_all(
        [Commentator(user_id=user.id, handle="first"), Commentator(user_id=user.id, handle="other")]
    )
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_handles_are_unique(db: AsyncSession) -> None:
    first, second = await new_user(db), await new_user(db, "other@example.com")
    db.add_all(
        [
            Commentator(user_id=first.id, handle="same"),
            Commentator(user_id=second.id, handle="same"),
        ]
    )
    with pytest.raises(IntegrityError):
        await db.commit()


async def test_the_account_is_never_loaded_behind_an_attribute_read(db: AsyncSession) -> None:
    """lazy="raise": a query that forgets joinedload fails here, not as an N+1 later."""
    user = await new_user(db)
    db.add(Commentator(user_id=user.id, handle="fan_cast"))
    await db.commit()
    db.expunge_all()

    stored = (await db.execute(select(Commentator))).scalar_one()
    with pytest.raises(Exception, match="lazy='raise'"):
        _ = stored.user
