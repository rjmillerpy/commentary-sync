import { SessionProvider } from "@commentary-sync/client/react";
import { PLAYLIST, STREAM, SYNC_MATCHED } from "@commentary-sync/client/testing";
import { act, renderHook } from "@testing-library/react-native";
import type { ReactNode } from "react";
import { AppState, type AppStateStatus } from "react-native";

import { TICK_MS } from "@/hooks/useDelayedPlayback";
import { useListenSession } from "@/hooks/useListenSession";
import { AUTO_CHECK_INTERVAL_MS, AUTO_LISTEN_SECONDS, SETTLE_MS } from "@/lib/autoSync";
import { Session } from "@/lib/session";
import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { RECORDING_SECONDS } from "@/lib/tvSync";
import { microphone } from "../_fakeAudio";
import { setOnline } from "../_fakeNetwork";
import { items } from "../_fakeSecureStore";
import { latestPlayer } from "../_fakeVideo";
import { listenerApi } from "../_render";

const STREAM_ROW = { ...STREAM, status: "live" as const };
const SYNC = "POST /streams/s-1/sync";

function signedIn({ children }: { children: ReactNode }) {
  return <SessionProvider createSession={() => new Session()}>{children}</SessionProvider>;
}

const advance = (ms: number) =>
  act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });

const syncs = (paths: string[]) => paths.filter((path) => path.startsWith(SYNC)).length;

/** Listening, playing 20 s behind live; `synced` first syncs by hand. */
async function listening({ synced = true } = {}) {
  const fake = listenerApi()
    .on("POST", "/streams/s-1/listener-playlist", { status: 200, body: PLAYLIST })
    .on("POST", "/streams/s-1/listening", { status: 204 })
    .on("GET", "/clock", { status: 200, body: { now: Date.now() / 1000 } })
    .on("POST", "/streams/s-1/sync", { status: 200, body: { ...SYNC_MATCHED, delay_seconds: 20 } });
  const hook = await renderHook(() => useListenSession(STREAM_ROW), { wrapper: signedIn });
  await advance(0);
  Object.assign(latestPlayer(), { currentTime: 300, currentOffsetFromLive: 10 });
  await advance(TICK_MS);
  if (synced) {
    await act(async () => {
      void hook.result.current.sync.start();
      await jest.advanceTimersByTimeAsync(RECORDING_SECONDS * 1_000);
    });
    await advance(TICK_MS);
  }
  return { ...hook, fake };
}

beforeEach(() => {
  jest.useFakeTimers();
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
  microphone.feed = Float32Array.from({ length: 40 * 48_000 }, (_, index) => Math.sin(index / 9) * ((index >> 13) % 4));
});
afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

test("after a sync, the TV is re-checked every few minutes, with the commentary muted, not paused", async () => {
  const { result, fake } = await listening();
  expect(result.current.delay).toBe(20);
  expect(syncs(fake.paths())).toBe(1);
  await act(async () => {
    await jest.advanceTimersByTimeAsync(AUTO_CHECK_INTERVAL_MS + 1_000); // into the check's listening
  });
  expect(result.current.sync.state).toEqual({ kind: "recording", auto: true });
  expect([latestPlayer().muted, latestPlayer().playing]).toEqual([true, true]);
  await advance(AUTO_LISTEN_SECONDS * 1_000);
  expect(syncs(fake.paths())).toBe(2);
  expect(latestPlayer().muted).toBe(false);
});

test("before the first sync, nothing is checked automatically", async () => {
  const { fake } = await listening({ synced: false });
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(0);
});

test("losing the connection and getting it back reloads the audio, then re-checks the TV", async () => {
  const { result, fake } = await listening();
  await act(() => setOnline(false));
  expect(result.current.isOnline).toBe(false);
  Object.assign(latestPlayer(), { status: "error", keepsFailing: true });
  await advance(TICK_MS);
  expect(result.current.playback.phase).toBe("reconnecting");
  latestPlayer().keepsFailing = false;
  await act(() => setOnline(true));
  expect(latestPlayer().reloads.length).toBeGreaterThan(0); // at once, not after a wait
  await advance(TICK_MS);
  expect(result.current.playback.phase).toBe("playing");
  await advance(SETTLE_MS + AUTO_LISTEN_SECONDS * 1_000);
  expect(syncs(fake.paths())).toBe(2); // the TV may have stalled on the same Wi-Fi
});

test("coming back to the app re-checks the TV", async () => {
  const listeners: ((state: AppStateStatus) => void)[] = [];
  jest.spyOn(AppState, "addEventListener").mockImplementation((_type, listener) => {
    listeners.push(listener as (state: AppStateStatus) => void);
    return { remove: jest.fn() } as unknown as ReturnType<typeof AppState.addEventListener>;
  });
  const { fake } = await listening();
  await act(() => listeners.forEach((listener) => listener("background")));
  await act(() => listeners.forEach((listener) => listener("active")));
  await advance(SETTLE_MS + AUTO_LISTEN_SECONDS * 1_000);
  expect(syncs(fake.paths())).toBe(2);
});

test("switched off, nothing is checked automatically", async () => {
  const { result, fake } = await listening();
  await act(() => result.current.setAutoSync(false));
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(1);
});

test("offline, the schedule waits for the connection", async () => {
  const { fake } = await listening();
  await act(() => setOnline(false));
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(1);
});
