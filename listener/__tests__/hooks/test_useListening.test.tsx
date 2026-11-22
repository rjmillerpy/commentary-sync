import { act, renderHook } from "@testing-library/react-native";

import { CHECK_IN_MS, useListening } from "@/hooks/useListening";
import { listenerApi, withAccess } from "../_render";

const ROUTE = "POST /streams/s-1/listening";

beforeEach(() => {
  jest.useFakeTimers();
});
afterEach(() => jest.useRealTimers());

const checkIns = (paths: string[]) => paths.filter((path) => path === ROUTE).length;

test("while playing, it checks in at once and every 20 seconds, signed in", async () => {
  const fake = listenerApi().on("POST", "/streams/s-1/listening", { status: 204 });
  await renderHook(() => useListening("s-1", true), { wrapper: withAccess });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(CHECK_IN_MS * 2);
  });
  expect(checkIns(fake.paths())).toBe(3);
  expect(fake.requests.find((request) => request.path === "/streams/s-1/listening")?.authorization).toBe("Bearer guest-1");
});

test("not playing, it doesn't check in, and stops when playing stops", async () => {
  const fake = listenerApi().on("POST", "/streams/s-1/listening", { status: 204 });
  const { rerender } = await renderHook(({ playing }: { playing: boolean }) => useListening("s-1", playing), {
    wrapper: withAccess,
    initialProps: { playing: false },
  });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(CHECK_IN_MS);
  });
  expect(checkIns(fake.paths())).toBe(0);
  await rerender({ playing: true });
  await rerender({ playing: false });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(CHECK_IN_MS * 3);
  });
  expect(checkIns(fake.paths())).toBe(1);
});

test("a failed check-in is shrugged off", async () => {
  listenerApi().on("POST", "/streams/s-1/listening", { status: 503, body: { detail: "Try again shortly" } });
  await renderHook(() => useListening("s-1", true), { wrapper: withAccess });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(CHECK_IN_MS);
  });
});
