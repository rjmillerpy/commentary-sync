"""Simulate a viewer's phone hearing a TV speaker across a noisy living room."""

import numpy as np
from scipy import signal

from app.simulation.broadcast import SOURCE_SAMPLE_RATE
from app.sync.errors import InvalidAudioError
from app.sync.schema import Samples

CLOCK_DRIFT = 100e-6  # the TV and phone clocks disagree by 100 parts per million
REVERB_SECONDS = 0.4
REVERB_DECAY = 6.9  # ln(1000): the tail falls 60 dB over REVERB_SECONDS
REVERB_LEVEL = 0.12
SPEAKER_BAND_HZ = (180.0, 3800.0)  # small speaker into a phone microphone
SPEAKER_FILTER_ORDER = 2
HISS_LEVEL = 0.3  # white noise relative to the babble
MICROPHONE_GAIN = (0.05, 0.6)
DB_PER_AMPLITUDE_DECADE = 20.0
LEVEL_FLOOR = 1e-9


def simulate_room(
    rng: np.random.Generator, samples: Samples, snr_db: float, babble: Samples
) -> Samples:
    """Return what the phone records: the audio after drift, reverb, the speaker
    and microphone response, room noise at snr_db, and an unknown gain."""
    if len(babble) <= len(samples):
        raise InvalidAudioError("babble must be longer than the audio it is mixed into")

    heard = _apply_speaker_response(_apply_reverb(rng, _apply_clock_drift(samples)))
    noise = _room_noise(rng, babble, len(heard))
    noise_gain = (
        heard.std() / (noise.std() + LEVEL_FLOOR) * 10 ** (-snr_db / DB_PER_AMPLITUDE_DECADE)
    )
    microphone_gain = rng.uniform(*MICROPHONE_GAIN)
    return np.asarray((heard + noise * noise_gain) * microphone_gain, dtype=np.float32)


def _apply_clock_drift(samples: Samples) -> Samples:
    drifted_length = int(len(samples) * (1 + CLOCK_DRIFT))
    return np.asarray(signal.resample(samples, drifted_length), dtype=np.float32)


def _apply_reverb(rng: np.random.Generator, samples: Samples) -> Samples:
    """Direct sound plus an exponentially decaying noise tail."""
    tail_samples = int(REVERB_SECONDS * SOURCE_SAMPLE_RATE)
    decay = np.exp(-REVERB_DECAY * np.arange(tail_samples) / tail_samples)
    impulse_response = rng.standard_normal(tail_samples) * decay * REVERB_LEVEL
    impulse_response[0] = 1.0
    return np.asarray(
        signal.fftconvolve(samples, impulse_response)[: len(samples)], dtype=np.float32
    )


def _apply_speaker_response(samples: Samples) -> Samples:
    band = signal.butter(
        SPEAKER_FILTER_ORDER, SPEAKER_BAND_HZ, btype="band", fs=SOURCE_SAMPLE_RATE, output="sos"
    )
    return np.asarray(signal.sosfilt(band, samples), dtype=np.float32)


def _room_noise(rng: np.random.Generator, babble: Samples, length: int) -> Samples:
    """A random stretch of people talking, plus microphone hiss."""
    start = int(rng.integers(0, len(babble) - length))
    hiss = HISS_LEVEL * babble.std() * rng.standard_normal(length)
    return np.asarray(babble[start : start + length] + hiss, dtype=np.float32)
