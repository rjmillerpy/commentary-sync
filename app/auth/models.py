"""Database tables for auth: accounts and their refresh-token sessions."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base

MAX_EMAIL_LENGTH = 254  # RFC 5321's limit on a forward path
MAX_DISPLAY_NAME_LENGTH = 50
MAX_PASSWORD_HASH_LENGTH = 255
TOKEN_HASH_LENGTH = 64  # SHA-256, hex


class User(Base):
    """One account, listener or commentator."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Stored lower-case, so the unique index treats Bob@x.com and bob@x.com as one.
    email: Mapped[str] = mapped_column(String(MAX_EMAIL_LENGTH), unique=True)
    display_name: Mapped[str] = mapped_column(String(MAX_DISPLAY_NAME_LENGTH))
    password_hash: Mapped[str] = mapped_column(String(MAX_PASSWORD_HASH_LENGTH))
    # Every access token carries the version it was issued under. Raising it
    # invalidates them all at once, without waiting for them to expire.
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshToken(Base):
    """One signed-in device. Only a hash of the token is stored, so a copy of
    the table can't be used to sign in."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Kept after use until it expires: a revoked token presented again means
    # it was copied, and every session of that account is ended.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
