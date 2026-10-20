import { act, renderHook, waitFor } from "@testing-library/react";

import { useMicrophone } from "@/hooks/useMicrophone";
import { type FakeMedia, installMedia } from "../_fakeMedia";

let media: FakeMedia;

beforeEach(() => {
  media = installMedia();
});

afterEach(() => jest.useRealTimers());

test("opens the default microphone and lists the inputs", async () => {
  const { result } = renderHook(useMicrophone);
  await waitFor(() => expect(result.current.devices).toHaveLength(2));
  expect(result.current.stream).toBe(media.opened[0]);
  expect(result.current.deviceId).toBeNull();
  expect(result.current.error).toBeNull();
});

test("choosing another microphone closes the first", async () => {
  const { result } = renderHook(useMicrophone);
  await waitFor(() => expect(result.current.stream).not.toBeNull());
  act(() => result.current.choose("usb-mic"));
  await waitFor(() => expect(media.opened).toHaveLength(2));
  await waitFor(() => expect(result.current.stream).toBe(media.opened[1]));
  expect(media.opened[0]!.track.stop).toHaveBeenCalled();
  expect(media.opened[1]!.track.deviceId).toBe("usb-mic");
});

test("reports the level as the mic picks up sound", async () => {
  jest.useFakeTimers();
  media.sampleByte = 255;
  const { result } = renderHook(useMicrophone);
  await waitFor(() => expect(result.current.stream).not.toBeNull());
  act(() => jest.advanceTimersByTime(100));
  expect(result.current.level).toBe(1);
});

test("a refused microphone is explained", async () => {
  media.failure = "NotAllowedError";
  const { result } = renderHook(useMicrophone);
  await waitFor(() => expect(result.current.error).toMatch(/blocked/));
  expect(result.current.stream).toBeNull();
});

test("regression: without a secure connection the hook explains instead of throwing", async () => {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
  const { result } = renderHook(useMicrophone);
  await waitFor(() => expect(result.current.error).toMatch(/secure \(https\) connection/));
  expect(result.current.stream).toBeNull();
});

test("unmounting closes the microphone and its meter (rule 71)", async () => {
  const { result, unmount } = renderHook(useMicrophone);
  await waitFor(() => expect(result.current.stream).not.toBeNull());
  unmount();
  expect(media.opened[0]!.track.stop).toHaveBeenCalled();
  expect(media.contexts[0]!.closed).toBe(true);
});

test("regression: a mic that opens after unmount is closed at once", async () => {
  const { unmount } = renderHook(useMicrophone);
  unmount(); // before getUserMedia resolves
  await waitFor(() => expect(media.opened).toHaveLength(1));
  await waitFor(() => expect(media.opened[0]!.track.stop).toHaveBeenCalled());
});

test("a failure after unmount is ignored", async () => {
  media.failure = "NotFoundError";
  const { result, unmount } = renderHook(useMicrophone);
  unmount();
  await waitFor(() => expect(media.constraints).toHaveLength(1));
  expect(result.current.error).toBeNull();
});
