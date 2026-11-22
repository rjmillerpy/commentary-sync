import { act, renderHook } from "@testing-library/react";

import { formatElapsed, useElapsed } from "@/hooks/useElapsed";

afterEach(() => jest.useRealTimers());

test.each([
  [5, "0:05"],
  [245, "4:05"],
  [3_723, "1:02:03"],
])("%s seconds read as %s", (seconds, text) => {
  expect(formatElapsed(seconds)).toBe(text);
});

test("ticks every second from the stream's start", async () => {
  jest.useFakeTimers({ now: Date.parse("2026-11-22T12:00:10Z") });
  const { result } = renderHook(() => useElapsed("2026-11-22T12:00:00Z"));
  expect(result.current).toBe("0:10");
  await act(async () => {
    await jest.advanceTimersByTimeAsync(2_000);
  });
  expect(result.current).toBe("0:12");
});

test("no stream, no clock", () => {
  const { result } = renderHook(() => useElapsed(null));
  expect(result.current).toBeNull();
});
