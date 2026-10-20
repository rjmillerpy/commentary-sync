"""Sessions: issue a token pair, rotate it on refresh, end it on sign-out.

A refresh token works once. Refreshing revokes it and issues a new pair, so a
stolen copy is only good until the real client next refreshes. When a revoked
token comes back, one of the two holders is an attacker and there is no way to
tell which, so every session of that account is ended.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.errors import InvalidTokenError
from app.auth.models import RefreshToken, User
from app.auth.schema import TokenPair
from app.auth.tokens import AccessClaims, create_access_token, hash_refresh_token, new_refresh_token
from app.common.config import Settings

logger = logging.getLogger(__name__)


async def start_session(
    db: AsyncSession, user: User, settings: Settings, *, now: datetime
) -> TokenPair:
    """A new token pair for `user`. The caller commits."""
    # Expired tokens are no use even for reuse detection; clearing them here
    # keeps each account's rows bounded by how often it signs in.
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.expires_at <= now)
    )
    refresh_token = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
    )
    access_token = create_access_token(
        AccessClaims(user_id=user.id, session_version=user.session_version),
        secret=settings.auth_secret.get_secret_value(),
        lifetime=timedelta(seconds=settings.access_token_seconds),
        now=now,
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_seconds,
    )


async def rotate_session(
    db: AsyncSession, refresh_token: str, settings: Settings, *, now: datetime
) -> TokenPair:
    """Trade a refresh token for a new pair. It is spent in one UPDATE, so two
    requests racing with the same token can't both get a pair."""
    token_hash = hash_refresh_token(refresh_token)
    spend = (
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .values(revoked_at=now)
        .returning(RefreshToken.user_id)
    )
    user_id = (await db.execute(spend)).scalar_one_or_none()
    if user_id is None:
        await _end_sessions_if_reused(db, token_hash, now=now)
        raise InvalidTokenError("refresh token rejected")

    # The foreign key cascades, so a spent token's account still exists.
    user = await db.get_one(User, user_id)
    pair = await start_session(db, user, settings, now=now)
    await db.commit()
    return pair


async def end_session(db: AsyncSession, refresh_token: str) -> None:
    """Sign one device out. Unknown tokens are ignored, so signing out twice is
    not an error.

    The row is deleted, not revoked: a revoked token coming back means theft,
    but a signed-out client retrying its old token is just a stale client.
    """
    await db.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token))
    )
    await db.commit()


async def end_all_sessions(db: AsyncSession, user_id: uuid.UUID, *, now: datetime) -> None:
    """Revoke every refresh token of an account and invalidate its access
    tokens now, rather than when they expire. The caller commits."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(
        update(User).where(User.id == user_id).values(session_version=User.session_version + 1)
    )


async def _end_sessions_if_reused(db: AsyncSession, token_hash: str, *, now: datetime) -> None:
    reused_by = select(RefreshToken.user_id).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_not(None),
        RefreshToken.expires_at > now,
    )
    user_id = (await db.execute(reused_by)).scalar_one_or_none()
    if user_id is None:
        return
    logger.warning("revoked refresh token reused: ending every session of user %s", user_id)
    await end_all_sessions(db, user_id, now=now)
    await db.commit()
