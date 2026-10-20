/** The matcher's audio features, computed where the audio is: on the phone.
 *
 * A port of app/sync/service.extract_features. Audio at 8 kHz is cut into
 * 32 ms frames every 10 ms (periodic Hann window, as scipy.signal.stft
 * uses); each frame's power is summed into 16 log-spaced bands between 300
 * and 3600 Hz; the log of those energies is differenced across 2 frames,
 * which cancels volume and the speaker's and microphone's EQ.
 *
 * Only these numbers leave the phone: from 16 band energies 100 times a
 * second, the sound can't be played back or the words recovered.
 * client/test/features.test.ts checks this against numbers app/sync computed.
 */

export const ANALYSIS_SAMPLE_RATE = 8_000;
export const HOP_SAMPLES = 80;
export const WINDOW_SAMPLES = 256;
export const BAND_COUNT = 16;
export const FRAMES_PER_SECOND = ANALYSIS_SAMPLE_RATE / HOP_SAMPLES;
const BAND_LOW_HZ = 300;
const BAND_HIGH_HZ = 3_600;
const DELTA_FRAMES = 2;
const RELATIVE_ENERGY_FLOOR = 1e-2;
const SILENCE_FLOOR = 1e-30;

/** Frames of BAND_COUNT values, one row after another. */
export interface Features {
  frames: number;
  values: Float32Array;
}

export function extractFeatures(samples: Float32Array): Features {
  if (samples.length < WINDOW_SAMPLES + DELTA_FRAMES * HOP_SAMPLES) {
    throw new RangeError(`audio is too short to analyse (${samples.length} samples)`);
  }
  const energies = bandEnergies(samples);
  const frames = energies.length / BAND_COUNT;
  const mean = energies.reduce((sum, energy) => sum + energy, 0) / energies.length;
  const floor = RELATIVE_ENERGY_FLOOR * mean + SILENCE_FLOOR;
  const logs = energies.map((energy) => Math.log(energy + floor));
  const deltaFrames = frames - DELTA_FRAMES;
  const values = new Float32Array(deltaFrames * BAND_COUNT);
  for (let index = 0; index < values.length; index += 1) {
    values[index] = logs[index + DELTA_FRAMES * BAND_COUNT]! - logs[index]!;
  }
  return { frames: deltaFrames, values };
}

/** Band energies per frame: frames × bands, row by row. */
function bandEnergies(samples: Float32Array): Float64Array {
  const window = periodicHann(WINDOW_SAMPLES);
  const scale = 1 / window.reduce((sum, weight) => sum + weight, 0); // scipy's "spectrum" scaling
  const bands = bandOfBin();
  const frames = 1 + Math.floor((samples.length - WINDOW_SAMPLES) / HOP_SAMPLES);
  const energies = new Float64Array(frames * BAND_COUNT);
  const real = new Float64Array(WINDOW_SAMPLES);
  const imaginary = new Float64Array(WINDOW_SAMPLES);
  for (let frame = 0; frame < frames; frame += 1) {
    const start = frame * HOP_SAMPLES;
    for (let index = 0; index < WINDOW_SAMPLES; index += 1) real[index] = samples[start + index]! * window[index]!;
    imaginary.fill(0);
    fft(real, imaginary);
    for (let bin = 0; bin <= WINDOW_SAMPLES / 2; bin += 1) {
      const band = bands[bin]!;
      if (band >= 0) energies[frame * BAND_COUNT + band]! += (real[bin]! ** 2 + imaginary[bin]! ** 2) * scale * scale;
    }
  }
  return energies;
}

/** Which band each FFT bin falls in, or -1 for none: low <= f < high, as app/sync slices. */
function bandOfBin(): Int8Array {
  const edges = Array.from(
    { length: BAND_COUNT + 1 },
    (_, index) => BAND_LOW_HZ * (BAND_HIGH_HZ / BAND_LOW_HZ) ** (index / BAND_COUNT),
  );
  const bands = new Int8Array(WINDOW_SAMPLES / 2 + 1).fill(-1);
  for (let bin = 0; bin < bands.length; bin += 1) {
    const frequency = (bin * ANALYSIS_SAMPLE_RATE) / WINDOW_SAMPLES;
    const band = edges.findIndex((low, index) => index < BAND_COUNT && frequency >= low && frequency < edges[index + 1]!);
    bands[bin] = band;
  }
  return bands;
}

/** scipy's default "hann" for a spectrogram: periodic, not symmetric. */
function periodicHann(size: number): Float64Array {
  return Float64Array.from({ length: size }, (_, index) => 0.5 - 0.5 * Math.cos((2 * Math.PI * index) / size));
}

/** In-place radix-2 FFT (Cooley-Tukey); the length must be a power of two. */
export function fft(real: Float64Array, imaginary: Float64Array): void {
  const size = real.length;
  for (let index = 1, swap = 0; index < size; index += 1) {
    let bit = size >> 1;
    for (; swap & bit; bit >>= 1) swap ^= bit;
    swap ^= bit;
    if (index < swap) {
      [real[index], real[swap]] = [real[swap]!, real[index]!];
      [imaginary[index], imaginary[swap]] = [imaginary[swap]!, imaginary[index]!];
    }
  }
  for (let length = 2; length <= size; length <<= 1) butterflies(real, imaginary, length);
}

function butterflies(real: Float64Array, imaginary: Float64Array, length: number): void {
  const angle = (-2 * Math.PI) / length;
  for (let start = 0; start < real.length; start += length) {
    for (let offset = 0; offset < length / 2; offset += 1) {
      const cos = Math.cos(angle * offset);
      const sin = Math.sin(angle * offset);
      const even = start + offset;
      const odd = even + length / 2;
      const oddReal = real[odd]! * cos - imaginary[odd]! * sin;
      const oddImaginary = real[odd]! * sin + imaginary[odd]! * cos;
      real[odd] = real[even]! - oddReal;
      imaginary[odd] = imaginary[even]! - oddImaginary;
      real[even] = real[even]! + oddReal;
      imaginary[even] = imaginary[even]! + oddImaginary;
    }
  }
}
