import { act, renderHook, waitFor } from "@testing-library/react";

import { useGate } from "@/hooks/useGate";
import type { GateLevels } from "@/lib/gate";
import { type FakeMedia, FakeStream, installMedia } from "../_fakeMedia";

let media: FakeMedia;

beforeEach(() => {
  media = installMedia();
});

const microphone = (deviceId = "default") => new FakeStream(deviceId) as unknown as MediaStream;

test("no microphone, no gate", () => {
  const { result } = renderHook(() => useGate(null));
  expect(result.current.track).toBeNull();
  expect(media.worklets).toHaveLength(0);
});

test("gates the microphone: its output is the track to go on air", async () => {
  const stream = microphone();
  const { result } = renderHook(() => useGate(stream));
  await waitFor(() => expect(result.current.track).toBe(media.destinations[0]!.track));
  expect(result.current.error).toBeNull();
  act(() => result.current.setThreshold(-30));
  expect(media.worklets[0]!.posted[0]).toBeCloseTo(0.001);
});

test("subscribers hear the levels until they unsubscribe", async () => {
  const stream = microphone();
  const { result } = renderHook(() => useGate(stream));
  await waitFor(() => expect(result.current.track).not.toBeNull());
  const heard: GateLevels[] = [];
  const unsubscribe = result.current.subscribe((levels) => heard.push(levels));
  media.worklets[0]!.post({ power: 1, openShare: 1 });
  unsubscribe();
  media.worklets[0]!.post({ power: 1, openShare: 1 });
  expect(heard).toEqual([{ levelDb: 0, openShare: 1 }]);
});

test("a new microphone gets a new gate, and the old one is closed (rule 71)", async () => {
  const { result, rerender } = renderHook(({ stream }) => useGate(stream), { initialProps: { stream: microphone() } });
  await waitFor(() => expect(result.current.track).not.toBeNull());
  rerender({ stream: microphone("usb-mic") });
  await waitFor(() => expect(result.current.track).toBe(media.destinations[1]!.track));
  expect(media.contexts[0]!.closed).toBe(true);
});

test("unmounting while the gate opens closes it as soon as it's open", async () => {
  const stream = microphone();
  const { unmount } = renderHook(() => useGate(stream));
  unmount();
  await waitFor(() => expect(media.contexts[0]?.closed).toBe(true));
});

test("a browser that can't run the gate is told so, and there's nothing to go on air", async () => {
  media.workletFailure = "NotSupportedError";
  const stream = microphone();
  const { result } = renderHook(() => useGate(stream));
  await waitFor(() => expect(result.current.error).toMatch(/can't run the TV check/));
  expect(result.current.track).toBeNull();
});
