/** Runs automatic re-checks (lib/autoSync.ts): every few minutes, and a few
 * seconds after anything that may have moved the TV. `triggers` are the
 * times such things happened (null for never); a newer one schedules a
 * check. Nothing runs while `enabled` is false or a sync is already going. */

import { useEffect, useRef } from "react";

import { AUTO_CHECK_INTERVAL_MS, SETTLE_MS } from "@/lib/autoSync";

interface AutoSyncOptions {
  enabled: boolean;
  isBusy: boolean;
  triggers: (number | null)[];
  check(): void;
}

export function useAutoSync({ enabled, isBusy, triggers, check }: AutoSyncOptions): void {
  // The latest values, read by timers without restarting them.
  const latest = useRef({ isBusy, check });
  useEffect(() => {
    latest.current = { isBusy, check };
  }, [isBusy, check]);
  const runIfFree = () => {
    if (!latest.current.isBusy) latest.current.check();
  };

  useEffect(() => {
    if (!enabled) return;
    const timer = setInterval(runIfFree, AUTO_CHECK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [enabled]);

  const newest = Math.max(0, ...triggers.map((at) => at ?? 0));
  const handled = useRef(newest); // whatever happened before enabling isn't news
  useEffect(() => {
    if (!enabled || newest <= handled.current) return;
    handled.current = newest;
    const timer = setTimeout(runIfFree, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [enabled, newest]);
}
