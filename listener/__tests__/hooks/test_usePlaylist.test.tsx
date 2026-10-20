import { NO_HLS_YET_DETAIL } from "@commentary-sync/client/api";
import { SessionProvider } from "@commentary-sync/client/react";
import { PLAYLIST } from "@commentary-sync/client/testing";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { PLAYLIST_RETRY_MS, usePlaylist } from "@/hooks/usePlaylist";
import { Session } from "@/lib/session";
import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { items } from "../_fakeSecureStore";
import { listenerApi } from "../_render";

const ROUTE = "/streams/s-1/listener-playlist";
const NOT_YET = { status: 409, body: { detail: NO_HLS_YET_DETAIL } };

function signedIn({ children }: { children: ReactNode }) {
  return <SessionProvider createSession={() => new Session()}>{children}</SessionProvider>;
}

beforeEach(() => items.set(REFRESH_TOKEN_KEY, "refresh-1"));
afterEach(() => jest.useRealTimers());

test("gets the playlist URL with the listener's token", async () => {
  const fake = listenerApi().on("POST", ROUTE, { status: 200, body: PLAYLIST });
  const { result } = await renderHook(() => usePlaylist("s-1"), { wrapper: signedIn });
  await waitFor(() => expect(result.current).toEqual({ kind: "ready", url: PLAYLIST.url }));
  expect(fake.requests.at(-1)?.authorization).toBe("Bearer access-2");
});

test("waits while the commentator's audio hasn't reached HLS, then plays", async () => {
  jest.useFakeTimers();
  listenerApi().on("POST", ROUTE, NOT_YET, { status: 200, body: PLAYLIST });
  const { result } = await renderHook(() => usePlaylist("s-1"), { wrapper: signedIn });
  await waitFor(() => expect(result.current).toEqual({ kind: "waiting" }));
  await act(async () => {
    await jest.advanceTimersByTimeAsync(PLAYLIST_RETRY_MS);
  });
  await waitFor(() => expect(result.current.kind).toBe("ready"));
});

test("an ended stream is a failure with the API's sentence", async () => {
  listenerApi().on("POST", ROUTE, { status: 409, body: { detail: "This stream has already ended" } });
  const { result } = await renderHook(() => usePlaylist("s-1"), { wrapper: signedIn });
  await waitFor(() => expect(result.current).toEqual({ kind: "failed", detail: "This stream has already ended" }));
});

test("leaving while waiting stops the retries (rule 71)", async () => {
  jest.useFakeTimers();
  const fake = listenerApi().on("POST", ROUTE, NOT_YET);
  const { unmount } = await renderHook(() => usePlaylist("s-1"), { wrapper: signedIn });
  await waitFor(() => expect(fake.paths()).toContain(`POST ${ROUTE}`));
  await unmount();
  const asked = fake.paths().length;
  await jest.advanceTimersByTimeAsync(PLAYLIST_RETRY_MS * 3);
  expect(fake.paths()).toHaveLength(asked);
});

test("a failure that isn't the API's is shown as it is", async () => {
  listenerApi();
  globalThis.fetch = (async () => ({ ok: true, status: 200, json: async () => ({ unexpected: true }) })) as unknown as typeof fetch;
  const { result } = await renderHook(() => usePlaylist("s-1"), { wrapper: signedIn });
  await waitFor(() => expect(result.current.kind).toBe("failed"));
});

test.each([
  ["no connection", "offline"],
  ["the server failing", "503"],
])("%s is waited out, not shown as the end", async (_case, cause) => {
  jest.useFakeTimers();
  const fake = listenerApi();
  if (cause === "offline") fake.on("POST", ROUTE, { status: 200, body: PLAYLIST });
  else fake.on("POST", ROUTE, { status: 503, body: { detail: "Service unavailable" } }, { status: 200, body: PLAYLIST });
  fake.offline = cause === "offline"; // from the start: even the sign-in refresh fails
  const { result } = await renderHook(() => usePlaylist("s-1"), { wrapper: signedIn });
  await waitFor(() => expect(result.current).toEqual({ kind: "waiting" }));
  fake.offline = false;
  await act(async () => {
    await jest.advanceTimersByTimeAsync(PLAYLIST_RETRY_MS);
  });
  await waitFor(() => expect(result.current.kind).toBe("ready"));
});
