"use client";

/** The TV check before going live (lib/tvCheck.ts), and the warning while
 * live if the TV gets louder than it was. */

import type { TvCheckValue } from "@/hooks/useTvCheck";
import { canGoLive, QUIET_SECONDS, TALK_SECONDS, type TvCheckResult, type Verdict } from "@/lib/tvCheck";

const VERDICTS: Record<Verdict, string> = {
  clear: "Your voice is well above the TV. Between your words, listeners hear nothing at all.",
  faint:
    "You can go live, but listeners may faintly hear the TV under your voice. Turn the TV down a little or move closer to your mic, then check again.",
  "too-loud":
    "Your mic hears the TV almost as well as you, so it would go out to listeners. Turn the TV down, move the mic closer to your mouth, or move away from the TV, then check again.",
  "no-voice": "We couldn't hear you. Check the microphone above, then check again.",
};

const PROMPTS = {
  quiet: "Stay quiet: listening to your TV…",
  talking: "Now talk, as if you're calling a play…",
};

const LOUDER =
  "Your mic is hearing more of the TV than at your check. Turn the TV down, or move closer to your mic.";

interface Props {
  check: TvCheckValue;
  /** The gate is running, and the commentator isn't live. */
  canCheck: boolean;
  isTvLouder: boolean;
  error: string | null;
}

export default function TvCheck({ check, canCheck, isTvLouder, error }: Props) {
  const { phase, result, start } = check;
  const isRunning = phase === "quiet" || phase === "talking";
  return (
    <section className="card" aria-labelledby="tv-title">
      <h2 id="tv-title">3. Check your TV</h2>
      <p className="hint">
        Listeners must hear you, not the game. Put the game on at the volume you&apos;ll watch it at, sit where
        you&apos;ll commentate, and start the check: stay quiet for {QUIET_SECONDS} seconds, then talk for {TALK_SECONDS}.
      </p>
      {error !== null && <p role="alert">{error}</p>}
      {isRunning && <p role="status">{PROMPTS[phase]}</p>}
      {result !== null && <Verdict result={result} />}
      {isTvLouder && <p role="alert">{LOUDER}</p>}
      <button type="button" disabled={!canCheck || isRunning} onClick={start}>
        {result === null ? "Start the TV check" : "Check again"}
      </button>
    </section>
  );
}

function Verdict({ result }: { result: TvCheckResult }) {
  const separation = Math.round(result.voiceDb - result.tvDb);
  return (
    <p role="status" className={canGoLive(result) ? "status live" : "status"}>
      {VERDICTS[result.verdict]}
      {result.verdict !== "no-voice" && ` Your voice is ${separation} dB louder than the TV.`}
    </p>
  );
}
