/** How many are listening to the commentator's live stream, checked every
 * 10 seconds while live. Null until known, or when the API can't count. */

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export const AUDIENCE_CHECK_MS = 10_000;

export function useAudience(streamId: string | null): number | null {
  const [listeners, setListeners] = useState<number | null>(null);

  useEffect(() => {
    if (streamId === null) return;
    let isCurrent = true;
    const check = () => {
      api
        .getStream(streamId)
        .then((stream) => {
          if (isCurrent) setListeners(stream.listeners);
        })
        .catch(() => undefined); // keep the last count; try again next time
    };
    check();
    const timer = setInterval(check, AUDIENCE_CHECK_MS);
    return () => {
      isCurrent = false;
      clearInterval(timer);
      setListeners(null);
    };
  }, [streamId]);

  return listeners;
}
