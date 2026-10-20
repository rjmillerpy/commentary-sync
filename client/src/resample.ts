/** Bringing a phone's microphone audio to the matcher's 8 kHz.
 *
 * Phones deliver 16, 44.1 or 48 kHz, whatever they were asked for. Above the
 * new rate's Nyquist frequency (4 kHz) the audio is first filtered out (a
 * windowed-sinc low-pass), or it would fold back into the bands the matcher
 * listens to; then samples are read off at the new rate, interpolating
 * between neighbours.
 */

const FILTER_TAPS = 63;
// The matcher listens up to 3.6 kHz; cut a little below the 4 kHz Nyquist.
const CUTOFF_FRACTION_OF_NYQUIST = 0.9;

export function resample(samples: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return samples;
  const filtered = fromRate > toRate ? lowPass(samples, (CUTOFF_FRACTION_OF_NYQUIST * toRate) / 2 / fromRate) : samples;
  const step = fromRate / toRate;
  const output = new Float32Array(Math.floor((samples.length - 1) / step) + 1);
  for (let index = 0; index < output.length; index += 1) {
    const position = index * step;
    const before = Math.floor(position);
    const after = Math.min(before + 1, filtered.length - 1);
    const fraction = position - before;
    output[index] = filtered[before]! * (1 - fraction) + filtered[after]! * fraction;
  }
  return output;
}

/** Windowed-sinc FIR low-pass at `cutoff` (cycles per sample), unity gain. */
function lowPass(samples: Float32Array, cutoff: number): Float32Array {
  const middle = (FILTER_TAPS - 1) / 2;
  const taps = Float64Array.from({ length: FILTER_TAPS }, (_, index) => {
    const offset = index - middle;
    const sinc = offset === 0 ? 2 * cutoff : Math.sin(2 * Math.PI * cutoff * offset) / (Math.PI * offset);
    const blackman = 0.42 - 0.5 * Math.cos((2 * Math.PI * index) / (FILTER_TAPS - 1)) + 0.08 * Math.cos((4 * Math.PI * index) / (FILTER_TAPS - 1));
    return sinc * blackman;
  });
  const gain = taps.reduce((sum, tap) => sum + tap, 0);
  const output = new Float32Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    let sum = 0;
    for (let tap = 0; tap < FILTER_TAPS; tap += 1) {
      const source = index + tap - middle;
      if (source >= 0 && source < samples.length) sum += samples[source]! * taps[tap]!;
    }
    output[index] = sum / gain;
  }
  return output;
}
