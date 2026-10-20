"""Database tables for events: the live broadcasts listeners pick commentary for."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base

MAX_TITLE_LENGTH = 200
MAX_TEAM_LENGTH = 100
MAX_SOURCE_LENGTH = 32
MAX_SOURCE_ID_LENGTH = 64
MAX_LEAGUE_LENGTH = 8
MAX_STATUS_LENGTH = 16


class Event(Base):
    """One broadcast, for example a single game."""

    __tablename__ = "events"
    __table_args__ = (
        # Re-importing a schedule updates the row the provider's ID points at.
        UniqueConstraint("source", "source_event_id", name="uq_events_source_event"),
        # The listing a listener sees is "this league, on now and next".
        Index("ix_events_league_starts_at", "league", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(MAX_SOURCE_LENGTH))
    source_event_id: Mapped[str] = mapped_column(String(MAX_SOURCE_ID_LENGTH))
    league: Mapped[str] = mapped_column(String(MAX_LEAGUE_LENGTH))
    title: Mapped[str] = mapped_column(String(MAX_TITLE_LENGTH))
    home_team: Mapped[str] = mapped_column(String(MAX_TEAM_LENGTH))
    away_team: Mapped[str] = mapped_column(String(MAX_TEAM_LENGTH))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(MAX_STATUS_LENGTH))
    # none_as_null: a missing list is SQL NULL, which NOT NULL rejects, not JSON `null`.
    networks: Mapped[list[str]] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
