/** Whether the stream being listened to has ended: checked every so often,
 * so a listener isn't left with silence and no reason for it. */

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export const STREAM_CHECK_MS = 15_000;

export function useStreamEnded(streamId: string): boolean {
  const [hasEnded, setHasEnded] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    const timer = setInterval(() => {
      api
        .getStream(streamId)
        .then((stream) => {
          if (isCurrent && stream.status === "ended") setHasEnded(true);
        })
        .catch(() => undefined); // offline for a moment: check again next time
    }, STREAM_CHECK_MS);
    return () => {
      isCurrent = false;
      clearInterval(timer);
    };
  }, [streamId]);

  return hasEnded;
}
