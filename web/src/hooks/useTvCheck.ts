"use client";

/** Running the TV check (lib/tvCheck.ts) against the voice gate's levels:
 * quiet, then talking, then the verdict, which sets the gate's threshold.
 * A new microphone needs a new check. */

import { useCallback, useEffect, useState } from "react";

import type { GateValue } from "@/hooks/useGate";
import { assessRoom, QUIET_SECONDS, TALK_SECONDS, type TvCheckResult } from "@/lib/tvCheck";

export type CheckPhase = "idle" | "quiet" | "talking" | "done";

export interface TvCheckValue {
  phase: CheckPhase;
  result: TvCheckResult | null;
  start(): void;
}

const MILLISECONDS_PER_SECOND = 1_000;
const NOT_STARTED = 0;

export function useTvCheck({ track, setThreshold, subscribe }: GateValue): TvCheckValue {
  const [run, setRun] = useState(NOT_STARTED);
  const [phase, setPhase] = useState<CheckPhase>("idle");
  const [result, setResult] = useState<TvCheckResult | null>(null);

  useEffect(() => {
    setRun(NOT_STARTED);
    setPhase("idle");
    setResult(null);
  }, [track]);

  useEffect(() => {
    if (run === NOT_STARTED) return;
    const quiet: number[] = [];
    const talking: number[] = [];
    let heard = quiet;
    setPhase("quiet");
    setResult(null);
    const unsubscribe = subscribe(({ levelDb }) => heard.push(levelDb));
    const talk = setTimeout(() => {
      heard = talking;
      setPhase("talking");
    }, QUIET_SECONDS * MILLISECONDS_PER_SECOND);
    const finish = setTimeout(
      () => {
        unsubscribe();
        const assessed = assessRoom(quiet, talking);
        setThreshold(assessed.thresholdDb);
        setResult(assessed);
        setPhase("done");
      },
      (QUIET_SECONDS + TALK_SECONDS) * MILLISECONDS_PER_SECOND,
    );
    return () => {
      clearTimeout(talk);
      clearTimeout(finish);
      unsubscribe();
    };
  }, [run, setThreshold, subscribe]);

  const start = useCallback(() => setRun((previous) => previous + 1), []);
  return { phase, result, start };
}
