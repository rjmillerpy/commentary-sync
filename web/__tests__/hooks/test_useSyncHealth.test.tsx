import { act, renderHook, waitFor } from "@testing-library/react";

import { AUDIENCE_CHECK_MS } from "@/hooks/useAudience";
import { useSyncHealth } from "@/hooks/useSyncHealth";
import { FakeApi, SYNC_HEALTH } from "../_fakeApi";

afterEach(() => jest.useRealTimers());

const authorized = <T,>(action: (token: string) => Promise<T>) => action("access-1");

test("not live: nothing is read", () => {
  const fake = new FakeApi().install();
  const { result } = renderHook(() => useSyncHealth({ authorized }, null));
  expect(result.current).toBeNull();
  expect(fake.requests).toEqual([]);
});

test("live: read at once and every 10 seconds, as the commentator", async () => {
  jest.useFakeTimers();
  const fake = new FakeApi()
    .on("GET", "/streams/s-1/sync-health", { status: 200, body: SYNC_HEALTH }, { status: 200, body: { ...SYNC_HEALTH, in_sync: 10 } })
    .install();
  const { result } = renderHook(() => useSyncHealth({ authorized }, "s-1"));
  await waitFor(() => expect(result.current).toEqual(SYNC_HEALTH));
  expect(fake.requests[0]?.authorization).toBe("Bearer access-1");
  await act(async () => {
    await jest.advanceTimersByTimeAsync(AUDIENCE_CHECK_MS);
  });
  expect(result.current?.in_sync).toBe(10);
});

test("a failed read keeps the last one; going off air clears it", async () => {
  jest.useFakeTimers();
  new FakeApi()
    .on("GET", "/streams/s-1/sync-health", { status: 200, body: SYNC_HEALTH }, { status: 503, body: { detail: "Try again shortly" } })
    .install();
  const { result, rerender } = renderHook(({ id }: { id: string | null }) => useSyncHealth({ authorized }, id), { initialProps: { id: "s-1" as string | null } });
  await waitFor(() => expect(result.current).toEqual(SYNC_HEALTH));
  await act(async () => {
    await jest.advanceTimersByTimeAsync(AUDIENCE_CHECK_MS);
  });
  expect(result.current).toEqual(SYNC_HEALTH);
  rerender({ id: null });
  expect(result.current).toBeNull();
});
