/** The TV check: how much louder the commentator is than their TV, at the
 * microphone, and the voice gate's threshold from that (lib/gate.ts).
 *
 * The commentator stays quiet with the game on for a few seconds, then talks
 * for a few. The TV's level is its loudest moments (crowd roars, a shouting
 * announcer); the voice's is a typical loud syllable. The gate opens a
 * little above the TV, or well below the voice if the room is quiet. Too
 * little room between them, and the gate can't keep the TV off air, so they
 * can't go live until they fix it. While live, the background is watched:
 * if the TV gets louder than it was at the check, they're told.
 *
 * The numbers are first guesses, to be tuned on real rooms. */

import { GATE_TIMING, SILENCE_DB } from "@/lib/gate";

export const QUIET_SECONDS = 5;
export const TALK_SECONDS = 5;

/** "clear": the TV stays off air. "faint": it may be faintly heard under
 * the commentator's voice. "too-loud": the gate can't separate them.
 * "no-voice": the commentator wasn't heard at all. */
export type Verdict = "clear" | "faint" | "too-loud" | "no-voice";

export interface TvCheckResult {
  verdict: Verdict;
  tvDb: number;
  voiceDb: number;
  thresholdDb: number;
}

const TV_PERCENTILE = 0.95;
const VOICE_PERCENTILE = 0.75;
const MIN_VOICE_DB = -60;
const MIN_SEPARATION_DB = 12;
const CLEAR_SEPARATION_DB = 20;
const GATE_ABOVE_TV_DB = 6;
const GATE_BELOW_VOICE_DB = 20;

const ON_AIR_VERDICTS: ReadonlySet<Verdict> = new Set(["clear", "faint"]);

/** Levels (dBFS) heard while quiet, then while talking. */
export function assessRoom(quiet: readonly number[], talking: readonly number[]): TvCheckResult {
  const tvDb = percentile(quiet, TV_PERCENTILE);
  const voiceDb = percentile(talking, VOICE_PERCENTILE);
  const thresholdDb = Math.max(tvDb + GATE_ABOVE_TV_DB, voiceDb - GATE_BELOW_VOICE_DB);
  return { verdict: verdictFor(tvDb, voiceDb), tvDb, voiceDb, thresholdDb };
}

function verdictFor(tvDb: number, voiceDb: number): Verdict {
  if (voiceDb < MIN_VOICE_DB) return "no-voice";
  const separation = voiceDb - tvDb;
  if (separation < MIN_SEPARATION_DB) return "too-loud";
  return separation < CLEAR_SEPARATION_DB ? "faint" : "clear";
}

export function canGoLive(result: TvCheckResult | null): boolean {
  return result !== null && ON_AIR_VERDICTS.has(result.verdict);
}

/** The value `share` of the way up `levels` (nearest rank); silence if empty. */
export function percentile(levels: readonly number[], share: number): number {
  if (levels.length === 0) return SILENCE_DB;
  const sorted = [...levels].sort((low, high) => low - high);
  const rank = Math.min(sorted.length - 1, Math.max(0, Math.ceil(share * sorted.length) - 1));
  return sorted[rank]!;
}

const WATCH_SECONDS = 10;
const BACKGROUND_PERCENTILE = 0.2;
const LOUDER_BY_DB = 6;
/** How many reports the live watch looks back over. */
export const WATCH_REPORTS = Math.round(WATCH_SECONDS / GATE_TIMING.reportSeconds);

/** Whether the room has been louder than the TV was at the check, through
 * the commentator's pauses, for the last WATCH_SECONDS. Speech has gaps, so
 * a low percentile of the levels is the background even while they talk. */
export function isTvLouder(recent: readonly number[], result: TvCheckResult): boolean {
  if (recent.length < WATCH_REPORTS) return false;
  return percentile(recent, BACKGROUND_PERCENTILE) > result.tvDb + LOUDER_BY_DB;
}
