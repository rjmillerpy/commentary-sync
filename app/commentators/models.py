"""Database tables for commentators: the public side of an account that broadcasts."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.common.models import Base

MAX_HANDLE_LENGTH = 30
MAX_BIO_LENGTH = 500


class Commentator(Base):
    """An account's commentator profile. Listeners find commentators by handle;
    the account's email is never part of it."""

    __tablename__ = "commentators"
    # Server-made columns (created_at, updated_at) come back with the INSERT or
    # UPDATE itself (RETURNING): reading one later would be a hidden query,
    # which async code can't make.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012  # SQLAlchemy's declared form

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Unique: one profile per account.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    # Stored lower-case, so the unique index treats Bob and bob as one handle.
    handle: Mapped[str] = mapped_column(String(MAX_HANDLE_LENGTH), unique=True)
    bio: Mapped[str] = mapped_column(String(MAX_BIO_LENGTH), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # lazy="raise": async code can't load it behind an attribute read, so every
    # query that needs the account says so (joinedload), and a forgotten one
    # fails in tests instead of becoming an N+1 in production.
    user: Mapped[User] = relationship(lazy="raise")
