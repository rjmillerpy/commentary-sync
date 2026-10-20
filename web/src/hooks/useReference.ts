/** While a stream is live, send the commentator's room audio to the API so
 * listeners can sync their TVs to it (lib/reference.ts). Best effort: if the
 * browser won't open the microphone a second time, the broadcast carries on
 * and listeners set their delay by hand. */

import { measureClockOffset } from "@commentary-sync/client/clock";
import type { SessionValue } from "@commentary-sync/client/react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { closeMicrophone, openMicrophone } from "@/lib/microphone";
import { recordRoom, ROOM_CONSTRAINTS } from "@/lib/reference";

export type ReferenceStatus = "off" | "on" | "unavailable";

const MILLISECONDS_PER_SECOND = 1_000;
const deviceTime = () => (performance.timeOrigin + performance.now()) / MILLISECONDS_PER_SECOND;

export function useReference(
  { authorized }: Pick<SessionValue, "authorized">,
  streamId: string | null,
  deviceId: string | null,
): ReferenceStatus {
  const [status, setStatus] = useState<ReferenceStatus>("off");

  useEffect(() => {
    if (streamId === null) return;
    let stop: (() => void) | null = null;
    let isCurrent = true;
    const start = async () => {
      const offset = await measureClockOffset(api.serverTime, deviceTime);
      const room = await openMicrophone(deviceId, ROOM_CONSTRAINTS);
      const stopRecording = await recordRoom(room, ({ pcm, capturedAt }) => {
        // A lost chunk is a gap in the reference, not a failure worth stopping for.
        void authorized((token) => api.sendReference(token, streamId, pcm, capturedAt + offset)).catch(() => undefined);
      });
      stop = () => {
        stopRecording();
        closeMicrophone(room);
      };
      if (isCurrent) setStatus("on");
      else stop(); // left while starting: undo at once
    };
    start().catch(() => {
      if (isCurrent) setStatus("unavailable");
    });
    return () => {
      isCurrent = false;
      stop?.();
      setStatus("off");
    };
  }, [authorized, streamId, deviceId]);

  return status;
}
