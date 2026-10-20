from collections.abc import Callable

import numpy as np
import pytest

from app.simulation import broadcast
from app.sync.schema import Samples

Synthesiser = Callable[[np.random.Generator, float], Samples]
SYNTHESISERS = [
    broadcast.synthesise_announcer,
    broadcast.synthesise_crowd,
    broadcast.synthesise_broadcast,
]
SYNTHESISER_IDS = ["announcer", "crowd", "broadcast"]


@pytest.mark.parametrize("synthesise", SYNTHESISERS, ids=SYNTHESISER_IDS)
@pytest.mark.parametrize("seconds", [0.5, 3.0], ids=["half-second", "three-seconds"])
def test_output_has_the_requested_length_and_stays_in_range(
    synthesise: Synthesiser, seconds: float, rng: np.random.Generator
) -> None:
    samples = synthesise(rng, seconds)
    assert len(samples) == int(seconds * broadcast.SOURCE_SAMPLE_RATE)
    assert samples.dtype == np.float32
    assert np.abs(samples).max() <= 1.0
    assert np.isfinite(samples).all()


@pytest.mark.parametrize("synthesise", SYNTHESISERS, ids=SYNTHESISER_IDS)
def test_same_seed_gives_the_same_audio(synthesise: Synthesiser) -> None:
    first = synthesise(np.random.default_rng(3), 2.0)
    second = synthesise(np.random.default_rng(3), 2.0)
    different = synthesise(np.random.default_rng(4), 2.0)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, different)


def test_broadcast_is_never_silent(rng: np.random.Generator) -> None:
    samples = broadcast.synthesise_broadcast(rng, 3.0)
    assert np.abs(samples).max() == pytest.approx(broadcast.OUTPUT_PEAK, rel=1e-3)


@pytest.mark.parametrize("bit_rate", [32_000, 96_000], ids=["32kbps", "96kbps"])
def test_codec_roundtrip_keeps_length_and_loudness(bit_rate: int, rng: np.random.Generator) -> None:
    original = broadcast.synthesise_broadcast(rng, 3.0)
    decoded = broadcast.codec_roundtrip(original, bit_rate)
    assert len(decoded) == pytest.approx(len(original), rel=0.1)
    assert decoded.std() == pytest.approx(original.std(), rel=0.2)
