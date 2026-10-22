"use client";

/** While live, whether the TV has got louder than it was at the TV check
 * (lib/tvCheck.ts isTvLouder), from the voice gate's levels. */

import { useEffect, useState } from "react";

import type { GateValue } from "@/hooks/useGate";
import { isTvLouder, type TvCheckResult, WATCH_REPORTS } from "@/lib/tvCheck";

export function useLeakWatch({ subscribe }: GateValue, result: TvCheckResult | null, isLive: boolean): boolean {
  const [isLouder, setIsLouder] = useState(false);

  useEffect(() => {
    if (!isLive || result === null) return;
    let recent: number[] = [];
    const unsubscribe = subscribe(({ levelDb }) => {
      recent = [...recent.slice(1 - WATCH_REPORTS), levelDb];
      setIsLouder(isTvLouder(recent, result));
    });
    return () => {
      unsubscribe();
      setIsLouder(false);
    };
  }, [subscribe, result, isLive]);

  return isLouder;
}
