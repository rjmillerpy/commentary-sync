/** Whether the phone is online, and when it last came back online. */

import { addNetworkStateListener, getNetworkStateAsync, type NetworkState } from "expo-network";
import { useEffect, useState } from "react";

export interface Connectivity {
  isConnected: boolean;
  /** When the connection last came back (ms since the epoch), or null. */
  reconnectedAt: number | null;
}

// Unknown counts as connected: only a definite "no" is shown as offline.
const isOnline = (state: NetworkState) => state.isConnected !== false && state.isInternetReachable !== false;

export function useConnectivity(): Connectivity {
  const [connectivity, setConnectivity] = useState<Connectivity>({ isConnected: true, reconnectedAt: null });

  useEffect(() => {
    let isCurrent = true;
    const update = (state: NetworkState) => {
      if (!isCurrent) return;
      const isConnected = isOnline(state);
      setConnectivity((previous) => ({
        isConnected,
        reconnectedAt: isConnected && !previous.isConnected ? Date.now() : previous.reconnectedAt,
      }));
    };
    void getNetworkStateAsync().then(update, () => undefined);
    const subscription = addNetworkStateListener(update);
    return () => {
      isCurrent = false;
      subscription.remove();
    };
  }, []);

  return connectivity;
}
