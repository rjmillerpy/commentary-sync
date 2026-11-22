"use client";

/** The studio: sign in, become a commentator, then pick, check and go live;
 * once live, the on-air view instead (components/OnAir.tsx). */

import { useCallback, useEffect, useState } from "react";

import CommentatorGate from "@/components/CommentatorGate";
import EventPicker from "@/components/EventPicker";
import GoLive from "@/components/GoLive";
import MicCheck from "@/components/MicCheck";
import OnAir from "@/components/OnAir";
import SignIn from "@/components/SignIn";
import { useAudience } from "@/hooks/useAudience";
import { type BroadcastPhase, useBroadcast } from "@/hooks/useBroadcast";
import { useMicrophone } from "@/hooks/useMicrophone";
import { useReference } from "@/hooks/useReference";
import { useSession } from "@/hooks/useSession";
import { useSyncHealth } from "@/hooks/useSyncHealth";
import type { Commentator, SportsEvent } from "@commentary-sync/client/schema";

export default function Studio() {
  const { status, signOut } = useSession();
  if (status === "restoring") return <p className="card">Signing you back in…</p>;
  if (status === "signed-out") return <SignIn />;
  return (
    <>
      <CommentatorGate>{(commentator) => <Desk commentator={commentator} />}</CommentatorGate>
      <button type="button" className="link" onClick={() => void signOut()}>
        Sign out
      </button>
    </>
  );
}

function Desk({ commentator }: { commentator: Commentator }) {
  const session = useSession();
  const microphone = useMicrophone();
  const broadcast = useBroadcast(session, commentator.handle);
  const liveStreamId = broadcast.phase === "live" ? (broadcast.stream?.id ?? null) : null;
  const referenceStatus = useReference(session, liveStreamId, microphone.deviceId);
  const listeners = useAudience(liveStreamId);
  const health = useSyncHealth(session, liveStreamId);
  const [chosen, setChosen] = useState<SportsEvent | null>(null);
  const isOnAir = ON_AIR.has(broadcast.phase);
  useLeaveWarning(broadcast.phase !== "idle");

  // A stream picked up after a reload is on its own event.
  const eventId = broadcast.stream?.event_id ?? chosen?.id ?? null;
  const track = microphone.stream?.getAudioTracks()[0] ?? null;
  const { start, resume } = broadcast;
  const onStart = useCallback(() => {
    if (eventId !== null && track !== null) void start(eventId, track);
  }, [eventId, track, start]);
  const onResume = useCallback(() => {
    if (track !== null) void resume(track);
  }, [track, resume]);

  if (isOnAir) {
    return (
      <OnAir
        broadcast={broadcast}
        gameTitle={chosen !== null && chosen.id === eventId ? chosen.title : null}
        listeners={listeners}
        health={health}
        referenceStatus={referenceStatus}
        canResume={track !== null}
        onResume={onResume}
      />
    );
  }
  return (
    <>
      <p className="greeting">
        Signed in as <strong>@{commentator.handle}</strong>
      </p>
      <EventPicker chosenId={eventId} isLocked={broadcast.phase !== "idle"} onChoose={setChosen} />
      <MicCheck microphone={microphone} isLocked={broadcast.phase !== "idle"} />
      <GoLive phase={broadcast.phase} missing={missingStep(eventId, track)} error={broadcast.error} onStart={onStart} />
    </>
  );
}

/** Everything after "Go live" was pressed and before the stream ended. */
const ON_AIR: ReadonlySet<BroadcastPhase> = new Set(["connecting", "live", "reconnecting", "interrupted", "ending"]);

function missingStep(eventId: string | null, track: MediaStreamTrack | null): string | null {
  if (eventId === null) return "Pick the game you're watching first.";
  if (track === null) return "Allow the microphone first.";
  return null;
}

/** Ask before closing or reloading the tab while on air. */
function useLeaveWarning(isOnAir: boolean): void {
  useEffect(() => {
    if (!isOnAir) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isOnAir]);
}
