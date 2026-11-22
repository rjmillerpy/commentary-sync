/** How the commentator's listeners are syncing to their TV (GET
 * /streams/{id}/sync-health), read every 10 seconds while live, alongside
 * the listener count. Null until known, or when the API can't say. */

import type { SyncHealth } from "@commentary-sync/client/schema";
import { useEffect, useState } from "react";

import { AUDIENCE_CHECK_MS } from "@/hooks/useAudience";
import type { SessionValue } from "@/hooks/useSession";
import { api } from "@/lib/api";

export function useSyncHealth({ authorized }: Pick<SessionValue, "authorized">, streamId: string | null): SyncHealth | null {
  const [health, setHealth] = useState<SyncHealth | null>(null);

  useEffect(() => {
    if (streamId === null) return;
    let isCurrent = true;
    const check = () => {
      authorized((token) => api.syncHealth(token, streamId))
        .then((read) => {
          if (isCurrent) setHealth(read);
        })
        .catch(() => undefined); // keep the last reading; try again next time
    };
    check();
    const timer = setInterval(check, AUDIENCE_CHECK_MS);
    return () => {
      isCurrent = false;
      clearInterval(timer);
      setHealth(null);
    };
  }, [authorized, streamId]);

  return health;
}
