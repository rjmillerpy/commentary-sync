"""Synthesise a fake sports broadcast: crowd, announcer and referee whistles."""

import io
from collections.abc import Iterator

import numpy as np
from numpy.typing import NDArray
from scipy import signal

from app.sync.audio import decode_audio, encode_aac
from app.sync.schema import Samples

SOURCE_SAMPLE_RATE = 16000
PEAK_FLOOR = 1e-9

PAUSE_PROBABILITY = 0.15
PAUSE_SECONDS = (0.2, 1.2)
SYLLABLE_SECONDS = (0.08, 0.28)
PITCH_HZ = (95.0, 170.0)
VOICED_PROBABILITY = 0.8  # the rest are noisy consonants
FORMANT_RANGES_HZ = ((300.0, 900.0), (900.0, 2300.0), (2300.0, 3400.0))
FORMANT_Q = 8.0

CROWD_BAND_HZ = (200.0, 3000.0)
CROWD_BAND_FILTER_ORDER = 2
CROWD_SWELL_CUTOFF_HZ = 0.3
CROWD_SWELL_FILTER_ORDER = 1
CROWD_SWELL_DEPTH = 1.5

WHISTLE_HZ = 2900.0
WHISTLE_SECONDS = (0.2, 0.7)
SECONDS_PER_WHISTLE = 12.0

CROWD_LEVEL = 0.5
ANNOUNCER_LEVEL = 0.6
WHISTLE_LEVEL = 0.3
OUTPUT_PEAK = 0.7

ADTS_CONTAINER = "adts"
AAC_CONTAINER = "aac"


def synthesise_announcer(rng: np.random.Generator, seconds: float) -> Samples:
    """Speech-like audio: pitched or noisy syllables separated by pauses."""
    total_samples = int(seconds * SOURCE_SAMPLE_RATE)
    speech = np.concatenate(list(_speech_segments(rng, total_samples)))[:total_samples]
    return _normalise(speech)


def synthesise_crowd(rng: np.random.Generator, seconds: float) -> Samples:
    """Band-limited noise whose loudness swells slowly, like a stadium."""
    total_samples = int(seconds * SOURCE_SAMPLE_RATE)
    band = signal.butter(
        CROWD_BAND_FILTER_ORDER, CROWD_BAND_HZ, btype="band", fs=SOURCE_SAMPLE_RATE, output="sos"
    )
    noise = signal.sosfilt(band, rng.standard_normal(total_samples))
    lowpass = signal.butter(
        CROWD_SWELL_FILTER_ORDER, CROWD_SWELL_CUTOFF_HZ, fs=SOURCE_SAMPLE_RATE, output="sos"
    )
    swell = signal.sosfilt(lowpass, rng.standard_normal(total_samples))
    envelope = np.exp(CROWD_SWELL_DEPTH * swell / (swell.std() + PEAK_FLOOR))
    return _normalise(noise * envelope)


def synthesise_broadcast(rng: np.random.Generator, seconds: float) -> Samples:
    crowd = CROWD_LEVEL * synthesise_crowd(rng, seconds)
    announcer = ANNOUNCER_LEVEL * synthesise_announcer(rng, seconds)
    whistles = WHISTLE_LEVEL * _whistle_track(rng, len(crowd), int(seconds / SECONDS_PER_WHISTLE))
    return (_normalise(crowd + announcer + whistles) * OUTPUT_PEAK).astype(np.float32)


def codec_roundtrip(samples: Samples, bit_rate: int) -> Samples:
    """AAC encode then decode, standing in for broadcast and streaming compression."""
    buffer = io.BytesIO()
    encode_aac(
        samples, SOURCE_SAMPLE_RATE, buffer, bit_rate=bit_rate, container_format=ADTS_CONTAINER
    )
    buffer.seek(0)
    return decode_audio(buffer, SOURCE_SAMPLE_RATE, container_format=AAC_CONTAINER)


def _speech_segments(rng: np.random.Generator, total_samples: int) -> Iterator[Samples]:
    """Yield pauses and syllables until total_samples are covered.

    Every segment is at least one sample long, so the loop always terminates.
    """
    produced = 0
    while produced < total_samples:
        is_pause = rng.random() < PAUSE_PROBABILITY
        seconds = rng.uniform(*(PAUSE_SECONDS if is_pause else SYLLABLE_SECONDS))
        length = max(1, int(seconds * SOURCE_SAMPLE_RATE))
        produced += length
        yield np.zeros(length, dtype=np.float32) if is_pause else _syllable(rng, length)


def _syllable(rng: np.random.Generator, length: int) -> Samples:
    """One syllable: a pulse train or noise shaped by three formant resonators."""
    time = np.arange(length) / SOURCE_SAMPLE_RATE
    is_voiced = rng.random() < VOICED_PROBABILITY
    pitch = rng.uniform(*PITCH_HZ)
    source = signal.sawtooth(2 * np.pi * pitch * time) if is_voiced else rng.standard_normal(length)
    formants = [
        signal.lfilter(
            *signal.iirpeak(rng.uniform(low, high), FORMANT_Q, fs=SOURCE_SAMPLE_RATE), source
        )
        for low, high in FORMANT_RANGES_HZ
    ]
    shaped = np.sum(formants, axis=0) * np.hanning(length)
    return np.asarray(shaped, dtype=np.float32)


def _whistle_track(rng: np.random.Generator, total_samples: int, count: int) -> Samples:
    """A silent track with `count` short whistle bursts at random positions."""
    track = np.zeros(total_samples, dtype=np.float32)
    max_length = int(WHISTLE_SECONDS[1] * SOURCE_SAMPLE_RATE)
    if total_samples <= max_length:
        return track
    starts = rng.integers(0, total_samples - max_length, size=count)
    lengths = (rng.uniform(*WHISTLE_SECONDS, size=count) * SOURCE_SAMPLE_RATE).astype(int)
    for start, length in zip(starts, lengths, strict=True):
        time = np.arange(length) / SOURCE_SAMPLE_RATE
        track[start : start + length] += np.sin(2 * np.pi * WHISTLE_HZ * time) * np.hanning(length)
    return track


def _normalise(samples: Samples | NDArray[np.float64]) -> Samples:
    """Scale so the loudest sample has magnitude 1."""
    peak = float(np.abs(samples).max()) if len(samples) else 0.0
    return np.asarray(samples / (peak + PEAK_FLOOR), dtype=np.float32)
