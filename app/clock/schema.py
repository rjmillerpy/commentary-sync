"""Response shapes for the clock."""

from app.common.schema import FrozenModel


class ServerTime(FrozenModel):
    """The server's clock, as seconds since the Unix epoch."""

    now: float
