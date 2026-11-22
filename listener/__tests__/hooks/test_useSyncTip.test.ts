import { act, renderHook } from "@testing-library/react-native";

import { TIP_LINGER_MS, useSyncTip } from "@/hooks/useSyncTip";
import { PREFERENCE_KEYS } from "@/lib/preferences";
import type { SyncStatusKind } from "@/lib/syncStatus";
import { items } from "../_fakeSecureStore";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test("shown until the status first changes, then for a little longer, then never again", async () => {
  const { result, rerender } = await renderHook(({ kind }: { kind: SyncStatusKind }) => useSyncTip(kind), {
    initialProps: { kind: "syncing" as SyncStatusKind },
  });
  expect(result.current).toBe(true);
  await act(async () => {
    await jest.advanceTimersByTimeAsync(TIP_LINGER_MS * 2);
  });
  expect(result.current).toBe(true); // no change yet
  await rerender({ kind: "synced" });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(TIP_LINGER_MS);
  });
  expect(result.current).toBe(false);
  expect(items.get(PREFERENCE_KEYS.syncTipSeen)).toBe("1");
});

test("once seen, it isn't shown", async () => {
  items.set(PREFERENCE_KEYS.syncTipSeen, "1");
  const { result } = await renderHook(() => useSyncTip("syncing"));
  expect(result.current).toBe(false);
});
