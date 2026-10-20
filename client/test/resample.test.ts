import assert from "node:assert/strict";
import { test } from "node:test";

import { resample } from "../src/resample.ts";

function tone(hz: number, rate: number, seconds: number): Float32Array {
  return Float32Array.from({ length: Math.round(rate * seconds) }, (_, index) => Math.sin((2 * Math.PI * hz * index) / rate));
}

function rms(samples: Float32Array, skip = 100): number {
  const middle = samples.subarray(skip, samples.length - skip);
  return Math.sqrt(middle.reduce((sum, sample) => sum + sample * sample, 0) / middle.length);
}

for (const rate of [48_000, 44_100, 16_000]) {
  test(`${rate} Hz becomes 8 kHz, the right length, keeping a 1 kHz tone`, () => {
    const output = resample(tone(1_000, rate, 1), rate, 8_000);
    assert.ok(Math.abs(output.length - 8_000) <= 1, `${output.length} samples`);
    assert.ok(Math.abs(rms(output) - Math.SQRT1_2) < 0.02, `rms ${rms(output)}`);
  });
}

test("sound above 4 kHz is filtered out rather than folded into the bands", () => {
  // 5 kHz at 48 kHz would alias to 3 kHz at 8 kHz without the filter.
  assert.ok(rms(resample(tone(5_000, 48_000, 1), 48_000, 8_000)) < 0.05);
});

test("audio already at 8 kHz is passed through", () => {
  const samples = tone(440, 8_000, 0.1);
  assert.equal(resample(samples, 8_000, 8_000), samples);
});

test("upsampling interpolates between samples", () => {
  assert.deepEqual(Array.from(resample(Float32Array.from([0, 1]), 4_000, 8_000)), [0, 0.5, 1]);
});
