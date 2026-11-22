"""Reading back a stream's HLS recording: what listeners hear, for a stretch
of wall-clock time.

Egress writes 2 s MPEG-TS segments of AAC (recorder.py), and the playlist
stamps them with the wall-clock time they were recorded
(`#EXT-X-PROGRAM-DATE-TIME`), so a stretch of time maps to segments. The
reader fetches the playlist and only the segments that cover the stretch,
from where listeners fetch them (`hls_base_url`), and decodes them with the
sync domain's decoder. It is the leak check's view of the broadcast
(leaks.py): the recording is exactly what listeners get, so a check of it
can't be fooled by a studio that misreports.
"""

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx2
from fastapi import Request

from app.common.config import Settings
from app.streams.recorder import PLAYLIST_NAME
from app.sync.audio import decode_audio
from app.sync.errors import AudioDecodeError
from app.sync.schema import Samples

logger = logging.getLogger(__name__)

PROGRAM_DATE_TIME = "#EXT-X-PROGRAM-DATE-TIME:"
SEGMENT_INFO = "#EXTINF:"
SEGMENT_FORMAT = "mpegts"
# A stretch longer than this is never asked for: a check is about 20 s.
MAX_SEGMENTS = 20
MAX_PLAYLIST_BYTES = 512 * 1024
MAX_SEGMENT_BYTES = 512 * 1024


@dataclass(frozen=True)
class Segment:
    uri: str
    starts_at: float  # wall-clock seconds since the epoch
    seconds: float

    @property
    def ends_at(self) -> float:
        return self.starts_at + self.seconds


@dataclass(frozen=True)
class Recording:
    samples: Samples
    starts_at: float  # when its first sample was recorded


def parse_playlist(text: str) -> list[Segment]:
    """The playlist's segments with their recording times. A segment's time
    is its own program-date-time if it has one, else the end of the one before;
    segments before the first program-date-time have no time and are left out."""
    segments: list[Segment] = []
    next_start: float | None = None
    seconds: float | None = None
    for line in (raw.strip() for raw in text.splitlines()):
        if line.startswith(PROGRAM_DATE_TIME):
            next_start = datetime.fromisoformat(line.removeprefix(PROGRAM_DATE_TIME)).timestamp()
            continue
        if line.startswith(SEGMENT_INFO):
            seconds = float(line.removeprefix(SEGMENT_INFO).split(",", 1)[0])
            continue
        if not line or line.startswith("#") or seconds is None:
            continue
        if next_start is not None:  # a segment URI, timed
            segments.append(Segment(uri=line, starts_at=next_start, seconds=seconds))
            next_start += seconds
        seconds = None
    return segments


def covering(segments: list[Segment], start: float, end: float) -> list[Segment] | None:
    """The segments that cover [start, end], or None if the playlist doesn't
    reach that far yet (or no longer reaches back)."""
    if not segments or segments[0].starts_at > start or segments[-1].ends_at < end:
        return None
    return [segment for segment in segments if segment.ends_at > start and segment.starts_at < end]


@dataclass(frozen=True)
class HlsReader:
    client: httpx2.AsyncClient  # its base_url is hls_read_url, else hls_base_url

    async def read(
        self, hls_path: str, start: float, end: float, sample_rate: int
    ) -> Recording | None:
        """The recording's audio from `start` to `end`, or None if it can't be
        had yet: not recorded that far, or the files couldn't be fetched."""
        try:
            playlist = await self._fetch(f"{hls_path}/{PLAYLIST_NAME}", MAX_PLAYLIST_BYTES)
            wanted = covering(parse_playlist(playlist.decode()), start, end)
            if wanted is None or len(wanted) > MAX_SEGMENTS:
                return None
            bodies = await asyncio.gather(
                *(self._fetch(f"{hls_path}/{segment.uri}", MAX_SEGMENT_BYTES) for segment in wanted)
            )
            samples = await asyncio.to_thread(_decode_all, bodies, sample_rate)
        except (httpx2.HTTPError, AudioDecodeError, ValueError) as error:
            # The type only: an HTTP error's message has the URL, and the path
            # is the recording's key.
            logger.warning("HLS recording unreadable: %s", type(error).__name__)
            return None
        return Recording(samples=samples, starts_at=wanted[0].starts_at)

    async def _fetch(self, path: str, max_bytes: int) -> bytes:
        response = await self.client.get(path)
        response.raise_for_status()
        if len(response.content) > max_bytes:
            raise ValueError("HLS file larger than expected")
        return response.content

    async def aclose(self) -> None:
        await self.client.aclose()


def _decode_all(bodies: list[bytes], sample_rate: int) -> Samples:
    """MPEG-TS segments are one stream cut in pieces: joined back, they decode
    as one, with one decoder. Decoded one by one, each would start with the
    decoder's warm-up (about one AAC frame), stretching the timeline."""
    return decode_audio(io.BytesIO(b"".join(bodies)), sample_rate, container_format=SEGMENT_FORMAT)


def create_hls_reader(
    settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
) -> HlsReader | None:
    """The reader for this deployment's recordings, or None when HLS is off."""
    if settings.hls_base_url is None:
        return None
    client = httpx2.AsyncClient(
        base_url=str(settings.hls_read_url or settings.hls_base_url),
        timeout=httpx2.Timeout(settings.hls_read_timeout_seconds),
        transport=transport,
    )
    return HlsReader(client=client)


def get_hls_reader(request: Request) -> HlsReader | None:
    """FastAPI dependency: the app's HLS reader, or None when HLS is off."""
    reader: HlsReader | None = request.app.state.hls_reader
    return reader
