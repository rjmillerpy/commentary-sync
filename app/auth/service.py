"""Accounts: register, sign in, and find who an access token belongs to."""

import logging
from datetime import datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import lockout, passwords
from app.auth.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidTokenError,
    LoginLockedError,
)
from app.auth.models import User
from app.auth.schema import Credentials, Registration, TokenPair
from app.auth.sessions import start_session
from app.auth.tokens import read_access_token
from app.common.config import Settings

logger = logging.getLogger(__name__)


def normalise_email(email: str) -> str:
    """The one form an email is stored and looked up in."""
    return email.strip().lower()


async def register(
    db: AsyncSession, registration: Registration, settings: Settings, *, now: datetime
) -> TokenPair:
    """Create an account and sign it in."""
    user = User(
        email=normalise_email(registration.email),
        display_name=registration.display_name,
        password_hash=await passwords.hash_password(registration.password.get_secret_value()),
    )
    db.add(user)
    # The unique index decides, not a SELECT first: two sign-ups racing for one
    # address would both pass a SELECT.
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise EmailTakenError("email already registered") from error
    pair = await start_session(db, user, settings, now=now)
    await db.commit()
    logger.info("account %s registered", user.id)
    return pair


async def log_in(
    db: AsyncSession, cache: Redis, credentials: Credentials, settings: Settings, *, now: datetime
) -> TokenPair:
    """Check the password and start a session, unless the account is locked out."""
    email = normalise_email(credentials.email)
    # Checked first: a locked account costs no hashing, even with the right password.
    locked_for = await lockout.seconds_locked(
        cache,
        email,
        max_failures=settings.login_max_failures,
        window_seconds=settings.login_lockout_seconds,
    )
    if locked_for:
        logger.warning("login refused: account locked for %d s", locked_for)
        raise LoginLockedError(locked_for)

    user = await _find_by_email(db, email)
    password = credentials.password.get_secret_value()
    stored_hash = user.password_hash if user is not None else passwords.UNKNOWN_ACCOUNT_HASH
    is_correct = await passwords.verify_password(stored_hash, password)
    if user is None or not is_correct:
        await lockout.record_failure(cache, email, window_seconds=settings.login_lockout_seconds)
        logger.info("login failed: %s", "wrong password" if user else "unknown email")
        raise InvalidCredentialsError("email or password is wrong")

    await lockout.clear_failures(cache, email)
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = await passwords.hash_password(password)
    pair = await start_session(db, user, settings, now=now)
    await db.commit()
    logger.info("account %s signed in", user.id)
    return pair


async def authenticate(db: AsyncSession, access_token: str, settings: Settings) -> User:
    """The account an access token belongs to.

    The account is read on every request, so a token stops working the moment
    its session version is raised or the account is deleted, not 15 minutes
    later when it expires.
    """
    claims = read_access_token(access_token, secret=settings.auth_secret.get_secret_value())
    user = await db.get(User, claims.user_id)
    is_current = user is not None and user.session_version == claims.session_version
    if user is None or not is_current:
        raise InvalidTokenError("access token no longer valid")
    return user


async def _find_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
