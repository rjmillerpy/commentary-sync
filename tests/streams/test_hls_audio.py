import numpy as np
import pytest
from pydantic import HttpUrl

from app.common.config import Settings
from app.simulation.broadcast import SOURCE_SAMPLE_RATE
from app.streams import hls_audio
from app.streams.hls_audio import HlsReader, Segment, covering, create_hls_reader, parse_playlist
from app.sync.schema import Samples
from app.sync.service import ANALYSIS_SAMPLE_RATE
from tests.streams.conftest import FakeHls

pytestmark = pytest.mark.anyio

START = 1_792_400_000.0
ONE_SEGMENT = b"#EXTM3U\n#EXT-X-PROGRAM-DATE-TIME:2026-10-19T08:53:20Z\n#EXTINF:2.0,\ns.ts\n"
PLAYLIST = """#EXTM3U
#EXT-X-TARGETDURATION:2
#EXTINF:2.000,
before.ts
#EXT-X-PROGRAM-DATE-TIME:2026-10-19T08:53:20.000+00:00
#EXTINF:2.000,
s00000.ts
#EXTINF:1.500,
s00001.ts
#EXT-X-PROGRAM-DATE-TIME:2026-10-19T08:53:30.000+00:00
#EXTINF:2.000,
s00002.ts
#EXT-X-ENDLIST
"""


def test_segments_carry_their_recording_times() -> None:
    assert parse_playlist(PLAYLIST) == [
        Segment("s00000.ts", START, 2.0),
        Segment("s00001.ts", START + 2, 1.5),  # follows on from the one before
        Segment("s00002.ts", START + 10, 2.0),  # its own time, after a gap
    ]  # "before.ts" has no time: left out


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (START + 1, START + 3, ["s00000.ts", "s00001.ts"]),
        (START, START + 2, ["s00000.ts"]),
        (START - 1, START + 2, None),  # from before the recording reaches back
        (START + 10, START + 13, None),  # not recorded that far yet
    ],
    ids=["two-segments", "exactly-one", "too-early", "too-late"],
)
def test_the_segments_that_cover_a_stretch(
    start: float, end: float, expected: list[str] | None
) -> None:
    found = covering(parse_playlist(PLAYLIST), start, end)
    assert (None if found is None else [segment.uri for segment in found]) == expected


def test_an_empty_playlist_covers_nothing() -> None:
    assert covering([], START, START + 1) is None


def tone(seconds: float, hz: float = 440.0) -> Samples:
    time = np.arange(int(seconds * SOURCE_SAMPLE_RATE)) / SOURCE_SAMPLE_RATE
    return (0.5 * np.sin(2 * np.pi * hz * time)).astype(np.float32)


async def test_a_stretch_is_read_back_from_the_segments_that_cover_it(
    hls_reader: HlsReader, fake_hls: FakeHls
) -> None:
    fake_hls.publish("rec", tone(10), starts_at=START)
    recording = await hls_reader.read("rec", START + 3, START + 7, ANALYSIS_SAMPLE_RATE)
    assert recording is not None
    assert recording.starts_at == pytest.approx(START + 2, abs=0.1)  # the segment holding START + 3
    assert len(recording.samples) / ANALYSIS_SAMPLE_RATE == pytest.approx(
        6, abs=0.5
    )  # three 2 s segments
    spectrum = np.abs(np.fft.rfft(recording.samples))
    assert np.argmax(spectrum) * ANALYSIS_SAMPLE_RATE / len(recording.samples) == pytest.approx(
        440, abs=5
    )


@pytest.mark.parametrize(
    "files",
    [
        {},  # no playlist
        {"/rec/index.m3u8": ONE_SEGMENT},  # segment gone
        {
            "/rec/index.m3u8": ONE_SEGMENT,
            "/rec/s.ts": b"not audio",
        },
        {"/rec/index.m3u8": b"#EXTM3U\n#EXT-X-PROGRAM-DATE-TIME:not-a-time\n#EXTINF:2.0,\ns.ts\n"},
        {"/rec/index.m3u8": b"x" * (hls_audio.MAX_PLAYLIST_BYTES + 1)},
    ],
    ids=["no-playlist", "missing-segment", "not-audio", "bad-time", "oversized"],
)
async def test_a_recording_that_cant_be_read_is_none(
    hls_reader: HlsReader, fake_hls: FakeHls, files: dict[str, bytes]
) -> None:
    fake_hls.files.update(files)
    assert await hls_reader.read("rec", START, START + 2, ANALYSIS_SAMPLE_RATE) is None


async def test_a_stretch_longer_than_any_check_is_refused(
    hls_reader: HlsReader, fake_hls: FakeHls
) -> None:
    fake_hls.publish("rec", tone(60), starts_at=START)
    assert await hls_reader.read("rec", START, START + 50, ANALYSIS_SAMPLE_RATE) is None


def test_with_hls_off_there_is_no_reader(settings: Settings) -> None:
    assert create_hls_reader(settings) is None


async def test_a_failure_never_logs_the_recordings_secret_path(
    hls_reader: HlsReader, caplog: pytest.LogCaptureFixture
) -> None:
    """Security: the random path is the only key to a recording (README, HLS)."""
    assert await hls_reader.read("secret-path-123", START, START + 2, ANALYSIS_SAMPLE_RATE) is None
    assert "secret-path-123" not in caplog.text
    assert "HTTPStatusError" in caplog.text


def test_the_api_reads_from_its_own_address_when_it_has_one(settings: Settings) -> None:
    """Inside the compose network the API can't use the address phones use."""
    public = settings.model_copy(update={"hls_base_url": HttpUrl("http://localhost:8080")})
    reader = create_hls_reader(public)
    assert reader is not None and str(reader.client.base_url) == "http://localhost:8080/"
    internal = public.model_copy(update={"hls_read_url": HttpUrl("http://hls:8080")})
    reader = create_hls_reader(internal)
    assert reader is not None and str(reader.client.base_url) == "http://hls:8080/"
