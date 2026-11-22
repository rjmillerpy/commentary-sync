/** The sync status explains itself once (UI rule 7.2: a coach mark the
 * first time it changes, not a tutorial up front): the tip shows until the
 * status first changes, and the phone remembers it was seen. */

import { useEffect, useRef, useState } from "react";

import { PREFERENCE_KEYS, readFlag, writeFlag } from "@/lib/preferences";
import type { SyncStatusKind } from "@/lib/syncStatus";

export function useSyncTip(kind: SyncStatusKind): boolean {
  const [isShown, setIsShown] = useState(() => !readFlag(PREFERENCE_KEYS.syncTipSeen));
  const first = useRef(kind);
  useEffect(() => {
    if (!isShown || kind === first.current) return;
    // Seen it change once; from now on it explains itself.
    const timer = setTimeout(() => {
      writeFlag(PREFERENCE_KEYS.syncTipSeen);
      setIsShown(false);
    }, TIP_LINGER_MS);
    return () => clearTimeout(timer);
  }, [isShown, kind]);
  return isShown;
}

/** Long enough to read the tip next to the status it just changed to. */
export const TIP_LINGER_MS = 15_000;
