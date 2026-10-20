/** Keeping in sync without being asked.
 *
 * After the first sync, the listener's TV can drift from the commentary: they
 * pause it, an ad break runs a different length, a streaming TV stalls on bad
 * Wi-Fi. Only listening to the TV again can tell, so the app re-checks every
 * few minutes, and soon after anything likely to have moved it (the phone's
 * connection coming back, the app coming back to the front, playback
 * recovering). A re-check listens for less time than a sync the listener asks
 * for, mutes the commentary meanwhile (pausing would shift it), and only
 * changes the delay when the TV really moved.
 */

import { DELAY_TOLERANCE_SECONDS } from "@/lib/delay";
import type { DelayPlan } from "@/lib/tvSync";

const MINUTE_MS = 60_000;
const AUTO_CHECK_MINUTES = 5;
export const AUTO_CHECK_INTERVAL_MS = AUTO_CHECK_MINUTES * MINUTE_MS;
/** How long an automatic check listens: shorter than a requested sync. */
export const AUTO_LISTEN_SECONDS = 6;
/** After a reconnect or a return to the app, the TV and the stream need a
 * moment to settle before listening means anything. */
export const SETTLE_MS = 5_000;
/** Misses in a row before the listener is told auto-sync can't hear the TV. */
export const MISSES_BEFORE_NOTICE = 3;
const BACKOFF_FIRST_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export type RecheckOutcome = { kind: "keep" } | { kind: "adjust"; plan: DelayPlan };

/** What a re-check means for the delay now in use. */
export function judgeRecheck(plan: DelayPlan, currentDelay: number): RecheckOutcome {
  const hasMoved = plan.pauseTv > 0 || Math.abs(plan.delay - currentDelay) > DELAY_TOLERANCE_SECONDS;
  return hasMoved ? { kind: "adjust", plan } : { kind: "keep" };
}

/** How long to wait before reconnecting attempt `attempt` (0-based): 1, 2,
 * 4, 8 ... seconds, at most 30. */
export function backoffMs(attempt: number): number {
  return Math.min(BACKOFF_MAX_MS, BACKOFF_FIRST_MS * 2 ** attempt);
}
