/** Holding the commentary a chosen number of seconds behind real time.
 *
 * The HLS segments carry the wall-clock time they were recorded, so the
 * player can say how far behind real time it is playing
 * (`currentOffsetFromLive`). Every tick compares that with the listener's
 * chosen delay and corrects: seek back or forward, or, when the recording
 * doesn't reach back far enough yet, pause until the delay has built up (the
 * way a TV's pause builds a delay).
 */

export const DEFAULT_DELAY_SECONDS = 10;
export const MAX_DELAY_SECONDS = 300;
export const DELAY_STEP_SECONDS = 0.5;
const BIG_DELAY_STEP_SECONDS = 5;
/** The nudges the listener has: big ones to get close, small ones to match. */
export const DELAY_NUDGES = [-BIG_DELAY_STEP_SECONDS, -DELAY_STEP_SECONDS, DELAY_STEP_SECONDS, BIG_DELAY_STEP_SECONDS];
/** Closer than this counts as on target: seeking for less is audible and pointless. */
export const DELAY_TOLERANCE_SECONDS = 0.5;

export interface PlaybackReading {
  /** Seconds behind real time, or null before the player knows. */
  offset: number | null;
  /** Seconds into the recording. */
  position: number;
  /** Paused on purpose, to build up the delay. */
  isHolding: boolean;
}

export type Correction =
  | { kind: "none" }
  | { kind: "seek"; by: number }
  | { kind: "hold" }
  | { kind: "resume" };

const NONE: Correction = { kind: "none" };

export function correction({ offset, position, isHolding }: PlaybackReading, target: number): Correction {
  if (offset === null) return NONE;
  if (isHolding) return offset >= target ? { kind: "resume" } : NONE;
  const shortfall = target - offset; // positive: playing too close to live
  if (Math.abs(shortfall) <= DELAY_TOLERANCE_SECONDS) return NONE;
  if (shortfall > 0 && position < shortfall) return { kind: "hold" };
  return { kind: "seek", by: -shortfall };
}

/** A delay the listener can pick: on the 0.5 s grid, from 0 to 5 minutes. */
export function clampDelay(seconds: number): number {
  const stepped = Math.round(seconds / DELAY_STEP_SECONDS) * DELAY_STEP_SECONDS;
  return Math.min(MAX_DELAY_SECONDS, Math.max(0, stepped));
}

export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}
