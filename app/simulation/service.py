"""Run the synthetic benchmark: how accurately are noisy captures located?

This validates the maths and gives rough thresholds. It is not a substitute
for a test with real recordings of a broadcast.
"""

from itertools import product

import numpy as np
from scipy import signal

from app.simulation.broadcast import (
    SOURCE_SAMPLE_RATE,
    codec_roundtrip,
    synthesise_announcer,
    synthesise_broadcast,
)
from app.simulation.room import simulate_room
from app.simulation.schema import (
    BenchmarkConfig,
    BenchmarkReport,
    ConditionResult,
    NegativeControlResult,
    Scenario,
)
from app.sync import service as sync_service
from app.sync.schema import Match, Samples

# The commentator and the viewer receive the same broadcast through different encodes.
REFERENCE_BIT_RATE = 96_000
VIEWER_BIT_RATE = 32_000
BABBLE_SECONDS = 60.0
SECOND_VOICE_LEVEL = 0.7
EDGE_MARGIN_SECONDS = 5.0  # keep queries away from the ends of the reference
NEGATIVE_BROADCAST_SECONDS = 120.0
NEGATIVE_QUERY_SECONDS = 10.0
NEGATIVE_SNR_DB = 20.0
NEGATIVE_TRIALS_PER_TRIAL = 2
P95 = 95


def to_analysis_rate(samples: Samples) -> Samples:
    resampled = signal.resample_poly(samples, sync_service.ANALYSIS_SAMPLE_RATE, SOURCE_SAMPLE_RATE)
    return np.asarray(resampled, dtype=np.float32)


def build_scenario(rng: np.random.Generator, config: BenchmarkConfig) -> Scenario:
    broadcast = synthesise_broadcast(rng, config.reference_seconds)
    reference = to_analysis_rate(codec_roundtrip(broadcast, REFERENCE_BIT_RATE))
    babble = synthesise_announcer(rng, BABBLE_SECONDS) + SECOND_VOICE_LEVEL * synthesise_announcer(
        rng, BABBLE_SECONDS
    )
    return Scenario(
        reference_features=sync_service.extract_features(reference),
        viewer_feed=codec_roundtrip(broadcast, VIEWER_BIT_RATE),
        babble=babble,
    )


def run_condition(
    rng: np.random.Generator,
    scenario: Scenario,
    config: BenchmarkConfig,
    query_seconds: float,
    snr_db: float,
) -> ConditionResult:
    latest_start = config.reference_seconds - query_seconds - EDGE_MARGIN_SECONDS
    true_offsets = rng.uniform(EDGE_MARGIN_SECONDS, latest_start, size=config.trials)
    matches = [
        _locate_heard(rng, scenario, scenario.viewer_feed, float(offset), query_seconds, snr_db)
        for offset in true_offsets
    ]
    errors = np.abs(np.array([match.offset_seconds for match in matches]) - true_offsets)
    is_wrong = errors > config.tolerance_seconds
    is_confident = np.array([match.is_confident for match in matches])
    return ConditionResult(
        query_seconds=query_seconds,
        snr_db=snr_db,
        trials=config.trials,
        within_tolerance=int((~is_wrong).sum()),
        confident=int(is_confident.sum()),
        confident_but_wrong=int((is_confident & is_wrong).sum()),
        median_error_seconds=float(np.median(errors)),
        p95_error_seconds=float(np.percentile(errors, P95)),
        max_error_seconds=float(errors.max()),
    )


def run_negative_control(
    rng: np.random.Generator, scenario: Scenario, config: BenchmarkConfig
) -> NegativeControlResult:
    """Queries from a different broadcast must not match the reference confidently."""
    other_feed = codec_roundtrip(
        synthesise_broadcast(rng, NEGATIVE_BROADCAST_SECONDS), VIEWER_BIT_RATE
    )
    trials = config.trials * NEGATIVE_TRIALS_PER_TRIAL
    latest_start = NEGATIVE_BROADCAST_SECONDS - NEGATIVE_QUERY_SECONDS - EDGE_MARGIN_SECONDS
    starts = rng.uniform(0.0, latest_start, size=trials)
    matches = [
        _locate_heard(
            rng, scenario, other_feed, float(start), NEGATIVE_QUERY_SECONDS, NEGATIVE_SNR_DB
        )
        for start in starts
    ]
    return NegativeControlResult(
        trials=trials,
        false_confident=sum(match.is_confident for match in matches),
        max_score=max(match.score for match in matches),
    )


def run_benchmark(config: BenchmarkConfig) -> BenchmarkReport:
    rng = np.random.default_rng(config.seed)
    scenario = build_scenario(rng, config)
    conditions = tuple(
        run_condition(rng, scenario, config, query_seconds, snr_db)
        for query_seconds, snr_db in product(config.query_lengths_seconds, config.snr_levels_db)
    )
    return BenchmarkReport(
        conditions=conditions,
        negative_control=run_negative_control(rng, scenario, config),
    )


def _locate_heard(
    rng: np.random.Generator,
    scenario: Scenario,
    feed: Samples,
    start_seconds: float,
    query_seconds: float,
    snr_db: float,
) -> Match:
    """Play a slice of `feed` into the simulated room and locate what the phone heard."""
    start = int(start_seconds * SOURCE_SAMPLE_RATE)
    clean_slice = feed[start : start + int(query_seconds * SOURCE_SAMPLE_RATE)]
    heard = simulate_room(rng, clean_slice, snr_db, scenario.babble)
    query_features = sync_service.extract_features(to_analysis_rate(heard))
    return sync_service.locate_features(scenario.reference_features, query_features)
