import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { BAND_COUNT, extractFeatures, fft } from "../src/features.ts";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/features.json", import.meta.url), "utf8")) as {
  samples: number[];
  features: number[][];
};
const TOLERANCE = 1e-4; // measured: under 3e-6 (float64 here, float32 in scipy)

test("the phone's features are app/sync's features, to within rounding", () => {
  const features = extractFeatures(Float32Array.from(fixture.samples));
  assert.equal(features.frames, fixture.features.length);
  let worst = 0;
  fixture.features.forEach((row, frame) => {
    row.forEach((expected, band) => {
      worst = Math.max(worst, Math.abs(features.values[frame * BAND_COUNT + band]! - expected));
    });
  });
  assert.ok(worst < TOLERANCE, `largest difference ${worst}`);
});

test("too little audio to analyse is an error, as in app/sync", () => {
  assert.throws(() => extractFeatures(new Float32Array(415)), RangeError);
  assert.equal(extractFeatures(new Float32Array(416)).frames, 1);
});

test("the FFT of a pure tone is one bin and its mirror", () => {
  const size = 16;
  const real = Float64Array.from({ length: size }, (_, index) => Math.cos((2 * Math.PI * 3 * index) / size));
  const imaginary = new Float64Array(size);
  fft(real, imaginary);
  const magnitudes = Array.from(real, (value, index) => Math.round(Math.hypot(value, imaginary[index]!)));
  assert.deepEqual(magnitudes, [0, 0, 0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 8, 0, 0]);
});
