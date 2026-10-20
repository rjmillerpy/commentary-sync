"""Writes features.json: audio, and the features app/sync computes from it.

The phone computes the same features in TypeScript (client/src/features.ts),
and client/test/features.test.ts checks it against these numbers, so the two
implementations can't drift apart. tests/sync/test_features_fixture.py fails
if this file's output and the committed fixture differ. Regenerate with

    uv run python client/test/fixtures/features_fixture.py
"""

import json
from pathlib import Path

import numpy as np

from app.sync.service import ANALYSIS_SAMPLE_RATE, extract_features

FIXTURE = Path(__file__).with_name("features.json")
SECONDS = 1.5
SEED = 3
DECIMALS = 6


def fixture() -> dict[str, object]:
    """A chirp under bursts of noise: every band moves, nothing repeats."""
    rng = np.random.default_rng(SEED)
    count = int(SECONDS * ANALYSIS_SAMPLE_RATE)
    time = np.arange(count) / ANALYSIS_SAMPLE_RATE
    chirp = 0.3 * np.sin(2 * np.pi * (300 * time + 1000 * time**2))
    bursts = np.repeat(rng.uniform(0, 0.3, count // 400 + 1), 400)[:count]
    samples = np.round(chirp + bursts * rng.uniform(-1, 1, count), DECIMALS).astype(np.float32)
    features = extract_features(samples)
    return {
        "sample_rate": ANALYSIS_SAMPLE_RATE,
        "samples": samples.tolist(),
        "features": np.round(features.astype(np.float64), DECIMALS).tolist(),
    }


def main() -> None:
    FIXTURE.write_text(json.dumps(fixture()) + "\n")


if __name__ == "__main__":
    main()
