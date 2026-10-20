/** Tells the API this account is listening, every 20 s while it plays a
 * stream, so the commentator and other listeners see the count. The API
 * forgets a listener a minute after their last check-in. */

import { useSession } from "@commentary-sync/client/react";
import { useEffect } from "react";

import { api } from "@/lib/api";

export const CHECK_IN_MS = 20_000;

export function useListening(streamId: string, isPlaying: boolean): void {
  const { authorized } = useSession();

  useEffect(() => {
    if (!isPlaying) return;
    // A missed check-in only lowers the count for a moment.
    const checkIn = () => void authorized((token) => api.listening(token, streamId)).catch(() => undefined);
    checkIn();
    const timer = setInterval(checkIn, CHECK_IN_MS);
    return () => clearInterval(timer);
  }, [authorized, streamId, isPlaying]);
}
