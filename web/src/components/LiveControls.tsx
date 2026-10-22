"use client";

/** Go live, see that it worked, resume after an interruption, and end. */

import type { BroadcastPhase, BroadcastValue } from "@/hooks/useBroadcast";

const STATUS: Record<BroadcastPhase, string> = {
  idle: "Off air",
  starting: "Going live…",
  connecting: "Connecting your audio…",
  live: "Live: listeners can hear you",
  reconnecting: "Connection lost, reconnecting…",
  interrupted: "You're still live, but your audio isn't reaching listeners. Resume, or end the stream.",
  ending: "Ending…",
};

const ON_AIR: ReadonlySet<BroadcastPhase> = new Set(["live", "reconnecting", "interrupted"]);

interface Props {
  broadcast: BroadcastValue;
  canStart: boolean;
  onStart: () => void;
  onResume: () => void;
}

export default function LiveControls({ broadcast, canStart, onStart, onResume }: Props) {
  const { phase, error, end } = broadcast;
  return (
    <section className="card" aria-labelledby="live-title">
      <h2 id="live-title">4. Go live</h2>
      <p role="status" className={phase === "live" ? "status live" : "status"}>
        {STATUS[phase]}
      </p>
      {error !== null && <p role="alert">{error}</p>}
      {phase === "interrupted" && (
        <button type="button" disabled={!canStart} onClick={onResume}>
          Resume
        </button>
      )}
      {ON_AIR.has(phase) ? (
        <button type="button" className="danger" onClick={() => void end()}>
          End stream
        </button>
      ) : (
        <button type="button" disabled={!canStart || phase !== "idle"} onClick={onStart}>
          Go live
        </button>
      )}
    </section>
  );
}
