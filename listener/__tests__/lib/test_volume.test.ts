import { clampVolume, DEFAULT_VOLUME, VOLUME_STEP, VOLUME_STEPS } from "@/lib/volume";

test.each([
  ["a step", 0.3, 0.3],
  ["between steps, to the nearest", 0.34, 0.3],
  ["float error from adding steps", 0.1 + 0.2, 0.3],
  ["below silent", -0.2, 0],
  ["above full", 1.3, 1],
])("volume is clamped: %s", (_case, volume, expected) => {
  expect(clampVolume(volume)).toBe(expected);
});

test("ten steps, starting at full", () => {
  expect([VOLUME_STEPS, VOLUME_STEP, DEFAULT_VOLUME]).toEqual([10, 0.1, 1]);
});
