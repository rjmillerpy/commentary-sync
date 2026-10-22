import { act, renderHook } from "@testing-library/react";

import { useLeakWatch } from "@/hooks/useLeakWatch";
import { type TvCheckResult, WATCH_REPORTS } from "@/lib/tvCheck";
import { fakeGate } from "../_fakeGate";

const CHECKED: TvCheckResult = { verdict: "clear", tvDb: -50, voiceDb: -20, thresholdDb: -40 };

test("live: a TV turned up since the check is noticed, and one turned back down", () => {
  const gate = fakeGate();
  const { result } = renderHook(() => useLeakWatch(gate, CHECKED, true));
  act(() => gate.emit(-50, WATCH_REPORTS));
  expect(result.current).toBe(false);
  act(() => gate.emit(-35, WATCH_REPORTS));
  expect(result.current).toBe(true);
  act(() => gate.emit(-50, WATCH_REPORTS));
  expect(result.current).toBe(false);
});

test.each([
  ["off air", CHECKED, false],
  ["without a check", null, true],
])("%s, nothing is watched", (_case, checked, isLive) => {
  const gate = fakeGate();
  renderHook(() => useLeakWatch(gate, checked, isLive));
  expect(gate.listenerCount()).toBe(0);
});

test("going off air stops watching and clears the warning", () => {
  const gate = fakeGate();
  const { result, rerender } = renderHook(({ isLive }) => useLeakWatch(gate, CHECKED, isLive), {
    initialProps: { isLive: true },
  });
  act(() => gate.emit(-35, WATCH_REPORTS));
  expect(result.current).toBe(true);
  rerender({ isLive: false });
  expect(result.current).toBe(false);
  expect(gate.listenerCount()).toBe(0);
});
