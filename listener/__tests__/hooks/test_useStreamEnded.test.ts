import { ENDED_STREAM_FIXTURE } from "../_streams";
import { FakeApi, STREAM } from "@commentary-sync/client/testing";
import { act, renderHook } from "@testing-library/react-native";

import { STREAM_CHECK_MS, useStreamEnded } from "@/hooks/useStreamEnded";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

async function check(): Promise<void> {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(STREAM_CHECK_MS);
  });
}

test("a live stream stays live; an ended one is noticed at the next check", async () => {
  const fake = new FakeApi().on("GET", "/streams/s-1", { status: 200, body: STREAM }, { status: 200, body: ENDED_STREAM_FIXTURE }).install();
  const { result } = await renderHook(() => useStreamEnded("s-1"));
  await check();
  expect(result.current).toBe(false);
  await check();
  expect(result.current).toBe(true);
  expect(fake.paths()).toEqual(["GET /streams/s-1", "GET /streams/s-1"]);
});

test("a failed check is tried again later, not taken as an end", async () => {
  const fake = new FakeApi().install();
  fake.offline = true;
  const { result } = await renderHook(() => useStreamEnded("s-1"));
  await check();
  expect(result.current).toBe(false);
});

test("leaving stops the checks (rule 71)", async () => {
  const fake = new FakeApi().on("GET", "/streams/s-1", { status: 200, body: STREAM }).install();
  const { unmount } = await renderHook(() => useStreamEnded("s-1"));
  await unmount();
  await jest.advanceTimersByTimeAsync(STREAM_CHECK_MS * 3);
  expect(fake.paths()).toEqual([]);
});
