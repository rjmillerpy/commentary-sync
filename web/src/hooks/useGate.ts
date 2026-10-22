"use client";

/** The voice gate on the commentator's microphone (lib/gate.ts): open while
 * the microphone is, closed on change and on unmount (rule 71). Its levels
 * arrive 20 times a second, so they go to subscribers, not React state. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { type Gate, type GateLevels, openGate } from "@/lib/gate";

export type LevelsListener = (levels: GateLevels) => void;

export interface GateValue {
  /** The gated microphone, to go on air; null until the gate is running. */
  track: MediaStreamTrack | null;
  error: string | null;
  setThreshold(decibels: number): void;
  /** Calls `listener` with every report until the returned function is called. */
  subscribe(listener: LevelsListener): () => void;
}

const GATE_FAILURE = "This browser can't run the TV check. Use a recent Chrome, Edge, Firefox or Safari.";

export function useGate(microphone: MediaStream | null): GateValue {
  const [gate, setGate] = useState<Gate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const listeners = useRef(new Set<LevelsListener>());

  useEffect(() => {
    if (microphone === null) return;
    let opened: Gate | null = null;
    let isCurrent = true;
    openGate(microphone, (levels) => listeners.current.forEach((listener) => listener(levels)))
      .then((running) => {
        opened = running;
        if (!isCurrent) return running.close();
        setGate(running);
        setError(null);
      })
      .catch(() => {
        // Without a gate there is nothing safe to put on air: say so, and
        // going live stays disabled.
        if (isCurrent) setError(GATE_FAILURE);
      });
    return () => {
      isCurrent = false;
      opened?.close();
      setGate(null);
    };
  }, [microphone]);

  const setThreshold = useCallback((decibels: number) => gate?.setThreshold(decibels), [gate]);
  const subscribe = useCallback((listener: LevelsListener) => {
    listeners.current.add(listener);
    return () => void listeners.current.delete(listener);
  }, []);
  return useMemo(
    () => ({ track: gate?.track ?? null, error, setThreshold, subscribe }),
    [gate, error, setThreshold, subscribe],
  );
}
