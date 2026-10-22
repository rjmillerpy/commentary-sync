import { act, renderHook } from "@testing-library/react";

import { useTvCheck } from "@/hooks/useTvCheck";
import { QUIET_SECONDS, TALK_SECONDS } from "@/lib/tvCheck";
import { fakeGate } from "../_fakeGate";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

const wait = (seconds: number) => act(() => jest.advanceTimersByTime(seconds * 1_000));

test("quiet, then talking, then a verdict that sets the gate's threshold", () => {
  const gate = fakeGate();
  const { result } = renderHook(() => useTvCheck(gate));
  expect(result.current.phase).toBe("idle");
  act(() => result.current.start());
  expect(result.current.phase).toBe("quiet");
  act(() => gate.emit(-50, 10));
  wait(QUIET_SECONDS);
  expect(result.current.phase).toBe("talking");
  act(() => gate.emit(-20, 10));
  wait(TALK_SECONDS);
  expect(result.current.phase).toBe("done");
  expect(result.current.result).toMatchObject({ verdict: "clear", tvDb: -50, voiceDb: -20 });
  expect(gate.setThreshold).toHaveBeenCalledWith(-40);
  expect(gate.listenerCount()).toBe(0);
});

test("checking again starts over", () => {
  const gate = fakeGate();
  const { result } = renderHook(() => useTvCheck(gate));
  act(() => result.current.start());
  wait(QUIET_SECONDS + TALK_SECONDS);
  expect(result.current.result?.verdict).toBe("no-voice");
  act(() => result.current.start());
  expect(result.current.phase).toBe("quiet");
  expect(result.current.result).toBeNull();
});

test("a new microphone needs a new check, and one under way is dropped", () => {
  const first = fakeGate();
  const { result, rerender } = renderHook(({ gate }) => useTvCheck(gate), { initialProps: { gate: first } });
  act(() => result.current.start());
  rerender({ gate: { ...first, track: {} as MediaStreamTrack } });
  expect(result.current.phase).toBe("idle");
  wait(QUIET_SECONDS + TALK_SECONDS);
  expect(result.current.result).toBeNull();
  expect(first.setThreshold).not.toHaveBeenCalled();
});
