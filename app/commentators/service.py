"""Commentator profiles: become one, edit your own, and find others by handle."""

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.models import User
from app.commentators.errors import (
    AlreadyCommentatorError,
    CommentatorNotFoundError,
    HandleTakenError,
    NotACommentatorError,
)
from app.commentators.models import Commentator
from app.commentators.schema import CommentatorSignup, ProfileUpdate

logger = logging.getLogger(__name__)


def normalise_handle(handle: str) -> str:
    """The one form a handle is stored and looked up in."""
    return handle.strip().lower()


async def become_commentator(
    db: AsyncSession, user: User, signup: CommentatorSignup
) -> Commentator:
    """Give an account its commentator profile."""
    user_id = user.id  # read now: a rollback expires `user`
    commentator = Commentator(handle=normalise_handle(signup.handle), bio=signup.bio, user=user)
    db.add(commentator)
    # The unique indexes decide, not a SELECT first: two requests racing for
    # one handle, or from one account, would both pass a SELECT. Which index
    # refused the row is found afterwards, the same way on every database.
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        if await _find_by_user(db, user_id) is not None:
            raise AlreadyCommentatorError("account already has a commentator profile") from error
        raise HandleTakenError("handle already taken") from error
    await db.commit()
    logger.info("account %s became commentator %s", user_id, commentator.id)
    return commentator


async def get_own_profile(db: AsyncSession, user_id: uuid.UUID) -> Commentator:
    commentator = await _find_by_user(db, user_id)
    if commentator is None:
        raise NotACommentatorError("account has no commentator profile")
    return commentator


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, update: ProfileUpdate
) -> Commentator:
    commentator = await get_own_profile(db, user_id)
    commentator.bio = update.bio
    await db.commit()
    return commentator


async def get_by_handle(db: AsyncSession, handle: str) -> Commentator:
    query = _with_account().where(Commentator.handle == normalise_handle(handle))
    commentator = (await db.execute(query)).scalar_one_or_none()
    if commentator is None:
        raise CommentatorNotFoundError("no commentator with that handle")
    return commentator


async def list_commentators(db: AsyncSession, *, limit: int, offset: int) -> Sequence[Commentator]:
    """Commentators in handle order, each with its account, in one query."""
    query = _with_account().order_by(Commentator.handle).limit(limit).offset(offset)
    return (await db.execute(query)).scalars().all()


async def _find_by_user(db: AsyncSession, user_id: uuid.UUID) -> Commentator | None:
    query = _with_account().where(Commentator.user_id == user_id)
    return (await db.execute(query)).scalar_one_or_none()


def _with_account() -> Select[Commentator]:
    """Commentators joined to their accounts, which every response needs."""
    return select(Commentator).options(joinedload(Commentator.user))
