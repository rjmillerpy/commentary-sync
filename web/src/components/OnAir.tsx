"use client";

/** The studio while on air: what's live and for how long, the connection,
 * the listeners and their sync, and ending. Everything for setting up is
 * gone from the page until the stream ends. */

import EndStream from "@/components/EndStream";
import ListenerHealth from "@/components/ListenerHealth";
import SyncNote from "@/components/SyncNote";
import type { BroadcastPhase, BroadcastValue } from "@/hooks/useBroadcast";
import { useElapsed } from "@/hooks/useElapsed";
import type { ReferenceStatus } from "@/hooks/useReference";
import type { SyncHealth } from "@commentary-sync/client/schema";

const STATUS: Partial<Record<BroadcastPhase, string>> = {
  connecting: "Connecting your audio…",
  live: "Listeners can hear you",
  reconnecting: "Connection lost, reconnecting…",
  interrupted: "Your audio isn't reaching listeners. Resume, or end the stream.",
  ending: "Ending…",
};

interface Props {
  broadcast: BroadcastValue;
  gameTitle: string | null;
  listeners: number | null;
  health: SyncHealth | null;
  referenceStatus: ReferenceStatus;
  canResume: boolean;
  onResume: () => void;
}

export default function OnAir({ broadcast, gameTitle, listeners, health, referenceStatus, canResume, onResume }: Props) {
  const { phase, stream, error, end } = broadcast;
  const elapsed = useElapsed(stream?.started_at ?? null);
  const isLive = phase === "live";
  return (
    <section className="card on-air" aria-labelledby="on-air-title">
      <p className={isLive ? "badge live" : "badge"}>{isLive ? "● LIVE" : "○ NOT REACHING LISTENERS"}</p>
      <h2 id="on-air-title">{gameTitle ?? "Your stream"}</h2>
      <p role="status" className="status">
        {STATUS[phase]}
        {elapsed !== null && <span className="elapsed"> · on air {elapsed}</span>}
      </p>
      {error !== null && <p role="alert">{error}</p>}
      {phase === "interrupted" && (
        <button type="button" disabled={!canResume} onClick={onResume}>
          Resume
        </button>
      )}
      <ListenerHealth listeners={listeners} health={health} />
      <SyncNote status={referenceStatus} />
      {phase !== "ending" && <EndStream listeners={listeners} onEnd={() => void end()} />}
    </section>
  );
}
