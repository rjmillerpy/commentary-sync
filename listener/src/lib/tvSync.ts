/** Turning a sync result into what the listener does next.
 *
 * The API answers with how far the listener's TV is behind the
 * commentator's. That is the delay to play the commentary at, but the
 * commentary can't come sooner than HLS delivers it, a few seconds behind the
 * commentator. A TV less behind than that, or ahead, can only be lined up by
 * pausing the TV for the difference. */

import { clampDelay, DELAY_STEP_SECONDS } from "@/lib/delay";

/** How long the phone listens to the TV. */
export const RECORDING_SECONDS = 10;
/** The soonest the commentary can be played: HLS runs about 2-3 s behind the
 * commentator, plus room to hold steady. */
export const LIVE_FLOOR_SECONDS = 4;
/** A TV ahead of the commentator's isn't in their reference until their TV
 * catches up: a "not found" is retried a few times before giving up. */
export const NOT_FOUND_RETRIES = 3;
export const RETRY_MS = 5_000;

export interface DelayPlan {
  /** The delay to play the commentary at. */
  delay: number;
  /** Seconds to pause the TV for first; 0 when no pause is needed. */
  pauseTv: number;
}

export function planDelay(tvBehindSeconds: number): DelayPlan {
  if (tvBehindSeconds >= LIVE_FLOOR_SECONDS) return { delay: clampDelay(tvBehindSeconds), pauseTv: 0 };
  // Rounded up, so the TV ends up behind the floor, never short of it.
  const pause = Math.ceil((LIVE_FLOOR_SECONDS - tvBehindSeconds) / DELAY_STEP_SECONDS) * DELAY_STEP_SECONDS;
  return { delay: LIVE_FLOOR_SECONDS, pauseTv: pause };
}
