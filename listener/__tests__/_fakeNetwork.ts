/** expo-network, faked: the phone's connection is a boundary. Tests drop and
 * restore it with `setOnline`. */

import type { NetworkState } from "expo-network";

type Listener = (state: NetworkState) => void;

const listeners = new Set<Listener>();
export const network = { state: { isConnected: true, isInternetReachable: true } as NetworkState };

export async function getNetworkStateAsync(): Promise<NetworkState> {
  return network.state;
}

export function addNetworkStateListener(listener: Listener) {
  listeners.add(listener);
  return { remove: () => listeners.delete(listener) };
}

export function setOnline(isOnline: boolean): void {
  network.state = { isConnected: isOnline, isInternetReachable: isOnline };
  listeners.forEach((listener) => listener(network.state));
}

export function listenerCount(): number {
  return listeners.size;
}

export function reset(): void {
  listeners.clear();
  network.state = { isConnected: true, isInternetReachable: true };
}
