"use client";

/** The studio: sign in, become a commentator, then pick, check and go live. */

import { useCallback, useEffect, useState } from "react";

import AudienceCount from "@/components/AudienceCount";
import CommentatorGate from "@/components/CommentatorGate";
import EventPicker from "@/components/EventPicker";
import LiveControls from "@/components/LiveControls";
import MicCheck from "@/components/MicCheck";
import SignIn from "@/components/SignIn";
import SyncNote from "@/components/SyncNote";
import { useAudience } from "@/hooks/useAudience";
import { useBroadcast } from "@/hooks/useBroadcast";
import { useMicrophone } from "@/hooks/useMicrophone";
import { useReference } from "@/hooks/useReference";
import { useSession } from "@/hooks/useSession";
import type { Commentator } from "@commentary-sync/client/schema";

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
  const [chosenId, setChosenId] = useState<string | null>(null);
  const isLocked = broadcast.phase !== "idle";
  useLeaveWarning(isLocked);

  // A stream picked up after a reload is on its own event.
  const eventId = broadcast.stream?.event_id ?? chosenId;
  const track = microphone.stream?.getAudioTracks()[0] ?? null;
  const canStart = eventId !== null && track !== null;
  const { start, resume } = broadcast;
  const onStart = useCallback(() => {
    if (eventId !== null && track !== null) void start(eventId, track);
  }, [eventId, track, start]);
  const onResume = useCallback(() => {
    if (track !== null) void resume(track);
  }, [track, resume]);

  return (
    <>
      <p className="greeting">
        Signed in as <strong>@{commentator.handle}</strong>
      </p>
      <EventPicker chosenId={eventId} isLocked={isLocked} onChoose={setChosenId} />
      <MicCheck microphone={microphone} isLocked={isLocked} />
      <LiveControls broadcast={broadcast} canStart={canStart} onStart={onStart} onResume={onResume} />
      <AudienceCount listeners={listeners} />
      <SyncNote status={referenceStatus} />
    </>
  );
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
