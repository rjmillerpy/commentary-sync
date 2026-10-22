import { expect } from "@playwright/test";

import type { Heard } from "./listener";
import { TONE_HZ } from "./tone";

const TONE_TOLERANCE_HZ = 15; // between two and three analyser bins
const AUDIBLE_DBFS = -60;

/** The listener heard the commentator's microphone: the test tone, loud enough to hear. */
export function expectTheTone(heard: Heard): void {
  expect(Math.abs(heard.frequency - TONE_HZ), `loudest at ${heard.frequency} Hz`).toBeLessThan(
    TONE_TOLERANCE_HZ,
  );
  expect(heard.level).toBeGreaterThan(AUDIBLE_DBFS);
}

/** The listener heard nothing: the studio's voice gate kept the room off air. */
export function expectSilence(heard: Heard): void {
  expect(heard.level, `loudest at ${heard.level} dBFS`).toBeLessThan(AUDIBLE_DBFS);
}
