/** Holding the commentary a chosen number of seconds behind real time.
 *
 * The HLS segments carry the wall-clock time they were recorded, so the
 * player can say how far behind real time it is playing
 * (`currentOffsetFromLive`). Every tick compares that with the target delay
 * and corrects it the least noticeable way (UI rule 1.2):
 *
 * - within SYNC_TOLERANCE_SECONDS: nothing;
 * - up to RATE_LIMIT_SECONDS off: play 5% slower or faster (which nobody
 *   hears) until it's back: 20 s to win back a second. Full speed change
 *   all the way, since easing off near the end would take far longer, and a
 *   tick (half a second) moves it 0.025 s, so it can't overshoot;
 * - further off: seek, but at most once every SEEK_COOLDOWN_MS, and after
 *   SEEKS_BEFORE_STUCK seeks that didn't land, stop trying ("stuck"): the
 *   listener is told and can resync. Endless seeking is worse than being off;
 * - when the recording doesn't reach back far enough yet, pause until the
 *   delay has built up (the way a TV's pause builds a delay).
 */

export const DEFAULT_DELAY_SECONDS = 10;
export const MAX_DELAY_SECONDS = 300;
/** The grid delays snap to. */
export const DELAY_STEP_SECONDS = 0.1;
const BIG_NUDGE_SECONDS = 5;
const SMALL_NUDGE_SECONDS = 1;
/** The nudges for setting the delay by hand (sync off): big ones to get close, small ones to match. */
export const DELAY_NUDGES = [-BIG_NUDGE_SECONDS, -SMALL_NUDGE_SECONDS, SMALL_NUDGE_SECONDS, BIG_NUDGE_SECONDS];
/** Closer than this counts as in sync. */
export const SYNC_TOLERANCE_SECONDS = 0.25;
/** Up to this far off, playback speed corrects it; further, a seek does. */
export const RATE_LIMIT_SECONDS = 2;
export const MAX_RATE_CHANGE = 0.05;
export const SEEK_COOLDOWN_MS = 10_000;
export const SEEKS_BEFORE_STUCK = 3;
/** Fine-tune: the listener's own correction on top of the synced delay. */
export const FINE_TUNE_STEP_SECONDS = 0.1;
export const MAX_FINE_TUNE_SECONDS = 10;

export interface PlaybackReading {
  /** Seconds behind real time, or null before the player knows. */
  offset: number | null;
  /** Seconds into the recording. */
  position: number;
  /** Paused on purpose, to build up the delay. */
  isHolding: boolean;
}

/** What earlier ticks did, which decides whether this one may seek. */
export interface SeekHistory {
  /** When the last seek was (ms since the epoch), or null for never. */
  lastSeekAt: number | null;
  /** Seeks in a row that didn't bring it within RATE_LIMIT_SECONDS. */
  misses: number;
}

export const NO_SEEKS: SeekHistory = { lastSeekAt: null, misses: 0 };

export type Correction =
  | { kind: "none" }
  | { kind: "rate"; rate: number }
  | { kind: "seek"; by: number }
  | { kind: "wait" }
  | { kind: "stuck" }
  | { kind: "hold" }
  | { kind: "resume" };

const NONE: Correction = { kind: "none" };

export function correction(reading: PlaybackReading, target: number, history: SeekHistory, now: number): Correction {
  const { offset, position, isHolding } = reading;
  if (offset === null) return NONE;
  if (isHolding) return offset >= target ? { kind: "resume" } : NONE;
  const shortfall = target - offset; // positive: playing too close to live
  if (Math.abs(shortfall) <= SYNC_TOLERANCE_SECONDS) return NONE;
  if (Math.abs(shortfall) <= RATE_LIMIT_SECONDS) return { kind: "rate", rate: rateFor(shortfall) };
  if (shortfall > 0 && position < shortfall) return { kind: "hold" };
  if (history.misses >= SEEKS_BEFORE_STUCK) return { kind: "stuck" };
  const isCoolingDown = history.lastSeekAt !== null && now - history.lastSeekAt < SEEK_COOLDOWN_MS;
  return isCoolingDown ? { kind: "wait" } : { kind: "seek", by: -shortfall };
}

/** Slower when too close to live (the delay grows), faster when too far behind. */
function rateFor(shortfall: number): number {
  return shortfall > 0 ? 1 - MAX_RATE_CHANGE : 1 + MAX_RATE_CHANGE;
}

/** A seek's history after the tick that made `step`: a seek that came after
 * another one that didn't land is a miss; landing clears the count. */
export function nextHistory(history: SeekHistory, step: Correction, now: number): SeekHistory {
  if (step.kind === "seek") return { lastSeekAt: now, misses: history.lastSeekAt === null ? 0 : history.misses + 1 };
  if (step.kind === "none" || step.kind === "rate") return NO_SEEKS;
  return history;
}

/** A delay the listener can have: on the 0.1 s grid, from 0 to 5 minutes. */
export function clampDelay(seconds: number): number {
  return Math.min(MAX_DELAY_SECONDS, Math.max(0, onGrid(seconds, DELAY_STEP_SECONDS)));
}

export function clampFineTune(seconds: number): number {
  return Math.min(MAX_FINE_TUNE_SECONDS, Math.max(-MAX_FINE_TUNE_SECONDS, onGrid(seconds, FINE_TUNE_STEP_SECONDS)));
}

function onGrid(seconds: number, step: number): number {
  // Rounded twice: 0.1 isn't exact in binary, and 12.3 should read as 12.3.
  const DECIMALS = 10;
  return Math.round(Math.round(seconds / step) * step * DECIMALS) / DECIMALS;
}

export function formatSeconds(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

/** A signed offset: "+0.3 s", "−1.2 s", "0.0 s". */
export function formatOffset(seconds: number): string {
  if (seconds === 0) return formatSeconds(0);
  return `${seconds > 0 ? "+" : "−"}${formatSeconds(Math.abs(seconds))}`;
}

/** How far behind someone is, the way a clock reads: "0:42", "2:15". */
export function formatBehind(seconds: number): string {
  const SECONDS_PER_MINUTE = 60;
  const whole = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(whole / SECONDS_PER_MINUTE);
  return `${minutes}:${String(whole % SECONDS_PER_MINUTE).padStart(2, "0")}`;
}
