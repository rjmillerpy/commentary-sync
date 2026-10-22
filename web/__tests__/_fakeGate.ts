/** A voice gate (hooks/useGate.ts) whose levels the test plays. */

import type { GateValue, LevelsListener } from "@/hooks/useGate";

export interface FakeGate extends GateValue {
  setThreshold: jest.Mock;
  /** Sends `levelDb` to every subscriber, `count` times. */
  emit(levelDb: number, count?: number): void;
  listenerCount(): number;
}

export function fakeGate(track: MediaStreamTrack | null = {} as MediaStreamTrack): FakeGate {
  const listeners = new Set<LevelsListener>();
  return {
    track,
    error: null,
    setThreshold: jest.fn(),
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    emit(levelDb, count = 1) {
      for (let sent = 0; sent < count; sent += 1) listeners.forEach((listener) => listener({ levelDb, openShare: 0 }));
    },
    listenerCount: () => listeners.size,
  };
}
