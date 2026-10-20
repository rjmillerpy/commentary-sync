"""Database tables for streams: a commentator's broadcast over one event."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.commentators.models import Commentator
from app.common.models import Base

# A stream is live until it has an end time. The one source of truth for
# "live": there is no status column that could disagree with it.
IS_LIVE = text("ended_at IS NULL")
MAX_PARTICIPANT_SID_LENGTH = 64  # LiveKit's are "PA_" and 12 characters
MAX_RECORDING_ID_LENGTH = 64  # LiveKit's egress IDs are "EG_" and 12 characters
HLS_PATH_BYTES = 16  # 128 random bits: can't be guessed
HLS_PATH_LENGTH = 22  # HLS_PATH_BYTES in URL-safe base64, as secrets.token_urlsafe writes it


class Stream(Base):
    """One commentator, live on one event, from `started_at` to `ended_at`."""

    __tablename__ = "streams"
    __table_args__ = (
        # One live stream per commentator, enforced by the database, so two
        # "go live" requests racing can't both succeed. Ended streams don't count.
        Index(
            "uq_streams_live_commentator",
            "commentator_id",
            unique=True,
            postgresql_where=IS_LIVE,
            sqlite_where=IS_LIVE,
        ),
        # What listeners ask: who is live on this event, oldest stream first.
        Index("ix_streams_event_id_started_at", "event_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    commentator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("commentators.id", ondelete="CASCADE")
    )
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("events.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The commentator's audio connection, from LiveKit webhooks. `publisher_sid`
    # is LiveKit's ID for the latest connection, so a "left" for an older one
    # (a page reload replaces the connection) changes nothing. `publisher_left_at`
    # is set while the commentator is gone; the scheduler ends streams whose
    # commentator stays gone past the grace period.
    publisher_sid: Mapped[str | None] = mapped_column(String(MAX_PARTICIPANT_SID_LENGTH))
    publisher_left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The HLS recording of the room, started when the commentator first
    # connects. `hls_path` is the recording's directory: random, so it can't
    # be found from the stream's ID, and handed out only to signed-in
    # listeners. Set first, as a claim, so two joins can't start two
    # recordings; `recording_id` is LiveKit's egress ID once it has started.
    hls_path: Mapped[str | None] = mapped_column(String(HLS_PATH_LENGTH))
    recording_id: Mapped[str | None] = mapped_column(String(MAX_RECORDING_ID_LENGTH))

    # lazy="raise", as in commentators: every query that needs it says so.
    commentator: Mapped[Commentator] = relationship(lazy="raise")
