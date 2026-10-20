import { writeFileSync } from "node:fs";

import { ANALYSIS_SAMPLE_RATE, extractFeatures } from "../../client/src/features.ts";
import { resample } from "../../client/src/resample.ts";

// The fake microphone plays this file on a loop: what the commentator's room
// sounds like. It has two parts, both timed by a seeded random generator so
// nothing in the file repeats (a sync recording of any part of it has only
// one place to be found in the commentator's reference):
// - a 440 Hz tone in pulses of random length, loud: if a listener's loudest
//   frequency is TONE_HZ, they hear the commentator, not silence or noise.
//   The gaps keep the studio's noise suppression from learning it as
//   steady background noise and removing it;
// - quieter noise bursts of random length and loudness, like a TV.
export const TONE_FILE = "/tmp/e2e-tone.wav";
export const TONE_HZ = 440;
export const ROOM_SECONDS = 60;
const ROOM_SEED = 1;

const SAMPLE_RATE = 48_000;
const TONE_AMPLITUDE = 0.4;
const NOISE_MAX_AMPLITUDE = 0.3;
const BURST_MIN_SECONDS = 0.03;
const BURST_MAX_SECONDS = 0.3;
const PULSE_MIN_SECONDS = 0.4;
const PULSE_MAX_SECONDS = 1.2;
const GAP_MIN_SECONDS = 0.1;
const GAP_MAX_SECONDS = 0.4;
const BYTES_PER_SAMPLE = 2;
const WAV_HEADER_BYTES = 44;
const INT16_MAX = 0x7fff;

/** A deterministic 0..1 generator (mulberry32), so every run sounds the same. */
function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed);
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 2 ** 32;
  };
}

/** The room's samples: tone plus seeded noise bursts. `seed` picks the noise. */
export function roomSamples(seconds: number = ROOM_SECONDS, seed: number = ROOM_SEED): Float32Array {
  const samples = new Float32Array(Math.round(seconds * SAMPLE_RATE));
  const next = random(seed);
  const between = (low: number, high: number) => Math.round((low + next() * (high - low)) * SAMPLE_RATE);
  let burstEnd = 0;
  let level = 0;
  let pulseEnd = 0;
  let isToneOn = false;
  for (let index = 0; index < samples.length; index += 1) {
    if (index >= burstEnd) {
      burstEnd = index + between(BURST_MIN_SECONDS, BURST_MAX_SECONDS);
      level = next() * NOISE_MAX_AMPLITUDE;
    }
    if (index >= pulseEnd) {
      isToneOn = !isToneOn;
      pulseEnd = index + (isToneOn ? between(PULSE_MIN_SECONDS, PULSE_MAX_SECONDS) : between(GAP_MIN_SECONDS, GAP_MAX_SECONDS));
    }
    const tone = isToneOn ? TONE_AMPLITUDE * Math.sin((2 * Math.PI * TONE_HZ * index) / SAMPLE_RATE) : 0;
    samples[index] = tone + level * (next() * 2 - 1);
  }
  return samples;
}

/** 16-bit mono PCM WAV of `samples`. */
export function wav(samples: Float32Array): Buffer {
  const data = Buffer.alloc(samples.length * BYTES_PER_SAMPLE);
  samples.forEach((sample, index) => {
    data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, sample)) * INT16_MAX), index * BYTES_PER_SAMPLE);
  });
  return Buffer.concat([wavHeader(data.length), data]);
}

/** What a listener's phone sends if their TV played seconds `from`..`from +
 * seconds` of the room: the features of it, computed by the phone's own code
 * (client/src/features.ts), from 48 kHz as a phone delivers it. */
export function roomClipFeatures(from: number, seconds: number, seed: number = ROOM_SEED): Float32Array {
  const room = roomSamples(ROOM_SECONDS, seed);
  const heard = room.subarray(Math.round(from * SAMPLE_RATE), Math.round((from + seconds) * SAMPLE_RATE));
  return extractFeatures(resample(heard, SAMPLE_RATE, ANALYSIS_SAMPLE_RATE)).values;
}

function wavHeader(dataBytes: number): Buffer {
  const header = Buffer.alloc(WAV_HEADER_BYTES);
  header.write("RIFF", 0);
  header.writeUInt32LE(WAV_HEADER_BYTES - 8 + dataBytes, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16); // fmt chunk size
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(1, 22); // mono
  header.writeUInt32LE(SAMPLE_RATE, 24);
  header.writeUInt32LE(SAMPLE_RATE * BYTES_PER_SAMPLE, 28); // bytes per second
  header.writeUInt16LE(BYTES_PER_SAMPLE, 32); // block align
  header.writeUInt16LE(BYTES_PER_SAMPLE * 8, 34); // bits per sample
  header.write("data", 36);
  header.writeUInt32LE(dataBytes, 40);
  return header;
}

export function writeToneFile(): void {
  writeFileSync(TONE_FILE, wav(roomSamples()));
}
