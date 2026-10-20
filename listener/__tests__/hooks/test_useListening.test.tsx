import { SessionProvider } from "@commentary-sync/client/react";
import { act, renderHook } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { CHECK_IN_MS, useListening } from "@/hooks/useListening";
import { Session } from "@/lib/session";
import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { items } from "../_fakeSecureStore";
import { listenerApi } from "../_render";

const ROUTE = "POST /streams/s-1/listening";

function signedIn({ children }: { children: ReactNode }) {
  return <SessionProvider createSession={() => new Session()}>{children}</SessionProvider>;
}

beforeEach(() => {
  jest.useFakeTimers();
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
});
afterEach(() => jest.useRealTimers());

const checkIns = (paths: string[]) => paths.filter((path) => path === ROUTE).length;

test("while playing, it checks in at once and every 20 seconds, signed in", async () => {
  const fake = listenerApi().on("POST", "/streams/s-1/listening", { status: 204 });
  await renderHook(() => useListening("s-1", true), { wrapper: signedIn });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(CHECK_IN_MS * 2);
  });
  expect(checkIns(fake.paths())).toBe(3);
  expect(fake.requests.find((request) => request.path === "/streams/s-1/listening")?.authorization).toBe("Bearer access-2");
});

test("not playing, it doesn't check in, and stops when playing stops", async () => {
  const fake = listenerApi().on("POST", "/streams/s-1/listening", { status: 204 });
  const { rerender } = await renderHook(({ playing }: { playing: boolean }) => useListening("s-1", playing), {
    wrapper: signedIn,
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
  await renderHook(() => useListening("s-1", true), { wrapper: signedIn });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(CHECK_IN_MS);
  });
});
