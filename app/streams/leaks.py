"""Is the game's own sound going out in a commentator's stream? The seam.

A commentator's mic also hears their TV, and rebroadcasting the game is the
main legal risk, so the server checks streams itself, after listeners'
syncs, against what listeners actually get: the stream's own HLS recording
(hls_audio.py). How it checks is private, like the matcher: an installed
package registers a detector under the `commentary_sync.leak_detectors`
entry point group. Without one, nothing is checked, and every stream's game
audio is `unknown`.
"""

import logging
import uuid
from dataclasses import dataclass
from functools import cache
from importlib.metadata import entry_points
from typing import Protocol

from fastapi import BackgroundTasks
from redis.asyncio import Redis

from app.streams.hls_audio import HlsReader
from app.streams.models import Stream
from app.streams.schema import GameAudio
from app.sync.schema import Features

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "commentary_sync.leak_detectors"


@dataclass(frozen=True)
class ListenerTv:
    """A listener's TV, as their sync heard it: `features` (commentary muted),
    which the commentator's TV played starting at `played_at` (server time)."""

    features: Features
    played_at: float


class LeakDetector(Protocol):
    async def schedule(
        self,
        background: BackgroundTasks,
        reader: HlsReader,
        cache: Redis,
        stream: Stream,
        tv: ListenerTv,
    ) -> None:
        """After a listener's matched sync: check the stream, now or after the reply, or not."""
        ...

    async def verdict(self, cache: Redis, stream_id: uuid.UUID) -> GameAudio:
        """What the stream's checks add up to."""
        ...


class NoLeakDetector:
    """The public build's detector: checks nothing, knows nothing."""

    async def schedule(
        self,
        background: BackgroundTasks,
        reader: HlsReader,
        cache: Redis,
        stream: Stream,
        tv: ListenerTv,
    ) -> None:
        return None

    async def verdict(self, cache: Redis, stream_id: uuid.UUID) -> GameAudio:
        return GameAudio.UNKNOWN


@cache
def detector() -> LeakDetector:
    """The installed detector, or NoLeakDetector; read once per process."""
    installed = sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda point: point.name)
    if not installed:
        return NoLeakDetector()
    if len(installed) > 1:
        logger.warning("%d leak detectors installed; using %s", len(installed), installed[0].name)
    found: LeakDetector = installed[0].load()()
    return found


def get_leak_detector() -> LeakDetector:
    """FastAPI dependency: the detector, so tests can swap it."""
    return detector()
