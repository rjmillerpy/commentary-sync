import numpy as np
import pytest

from app.simulation.broadcast import SOURCE_SAMPLE_RATE, synthesise_announcer
from app.simulation.room import CLOCK_DRIFT, simulate_room
from app.simulation.service import to_analysis_rate
from app.sync import service as sync_service
from app.sync.errors import InvalidAudioError
from app.sync.schema import Samples

SLICE_START_SECONDS = 10.0
SLICE_SECONDS = 10.0


@pytest.fixture(scope="module")
def babble() -> Samples:
    return synthesise_announcer(np.random.default_rng(21), 30.0)


@pytest.fixture(scope="module")
def tv_audio(broadcast: Samples) -> Samples:
    start = int(SLICE_START_SECONDS * SOURCE_SAMPLE_RATE)
    return broadcast[start : start + int(SLICE_SECONDS * SOURCE_SAMPLE_RATE)]


def _match_score(reference: Samples, heard: Samples) -> float:
    return sync_service.locate(to_analysis_rate(reference), to_analysis_rate(heard)).score


def test_recording_is_slightly_longer_because_of_clock_drift(
    tv_audio: Samples, babble: Samples, rng: np.random.Generator
) -> None:
    heard = simulate_room(rng, tv_audio, 20.0, babble)
    assert heard.dtype == np.float32
    assert len(heard) == int(len(tv_audio) * (1 + CLOCK_DRIFT))
    assert np.isfinite(heard).all()


@pytest.mark.parametrize(
    ("quieter_room_db", "louder_room_db"), [(20.0, 0.0), (0.0, -10.0)], ids=["20-vs-0", "0-vs--10"]
)
def test_a_noisier_room_resembles_the_broadcast_less(
    broadcast: Samples,
    tv_audio: Samples,
    babble: Samples,
    quieter_room_db: float,
    louder_room_db: float,
) -> None:
    quiet = simulate_room(np.random.default_rng(1), tv_audio, quieter_room_db, babble)
    noisy = simulate_room(np.random.default_rng(1), tv_audio, louder_room_db, babble)
    assert _match_score(broadcast, quiet) > _match_score(broadcast, noisy)


def test_same_seed_gives_the_same_recording(tv_audio: Samples, babble: Samples) -> None:
    first = simulate_room(np.random.default_rng(2), tv_audio, 10.0, babble)
    second = simulate_room(np.random.default_rng(2), tv_audio, 10.0, babble)
    assert np.array_equal(first, second)


def test_babble_shorter_than_the_audio_is_rejected(
    tv_audio: Samples, rng: np.random.Generator
) -> None:
    with pytest.raises(InvalidAudioError):
        simulate_room(rng, tv_audio, 10.0, tv_audio[:100])
