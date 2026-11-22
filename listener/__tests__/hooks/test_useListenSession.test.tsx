import { PLAYLIST, STREAM, SYNC_MATCHED, SYNC_NOT_FOUND } from "@commentary-sync/client/testing";
import { act, renderHook } from "@testing-library/react-native";
import { AppState, type AppStateStatus, Linking } from "react-native";

import { TICK_MS } from "@/hooks/useDelayedPlayback";
import { useListenSession } from "@/hooks/useListenSession";
import { AUTO_CHECK_INTERVAL_MS, AUTO_LISTEN_SECONDS, SETTLE_MS } from "@/lib/autoSync";
import { PREFERENCE_KEYS } from "@/lib/preferences";
import { NOT_FOUND_RETRIES, RECORDING_SECONDS, RETRY_MS } from "@/lib/tvSync";
import { microphone } from "../_fakeAudio";
import { setOnline } from "../_fakeNetwork";
import { items } from "../_fakeSecureStore";
import { latestPlayer } from "../_fakeVideo";
import { listenerApi, withAccess } from "../_render";

const STREAM_ROW = { ...STREAM, status: "live" as const };
const SYNC = "POST /streams/s-1/sync";

const advance = (ms: number) =>
  act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });

const syncs = (paths: string[]) => paths.filter((path) => path.startsWith(SYNC)).length;

/** Opens a stream playing 10 s behind live: it syncs by itself, to 20 s
 * (or, with `heard: false`, doesn't hear the TV). */
async function listening({ heard = true } = {}) {
  const fake = listenerApi()
    .on("POST", "/streams/s-1/listener-playlist", { status: 200, body: PLAYLIST })
    .on("POST", "/streams/s-1/listening", { status: 204 })
    .on("GET", "/clock", { status: 200, body: { now: Date.now() / 1000 } })
    .on("POST", "/streams/s-1/sync", heard ? { status: 200, body: { ...SYNC_MATCHED, delay_seconds: 20 } } : { status: 200, body: SYNC_NOT_FOUND });
  const hook = await renderHook(() => useListenSession(STREAM_ROW), { wrapper: withAccess });
  await advance(0);
  Object.assign(latestPlayer(), { currentTime: 300, currentOffsetFromLive: 10 });
  await advance(RECORDING_SECONDS * 1_000);
  await advance(heard ? TICK_MS : (NOT_FOUND_RETRIES + 1) * RETRY_MS);
  return { ...hook, fake };
}

// Opening a stream syncs for real: 10 s of audio resampled and turned into
// features in JavaScript, which takes seconds of CPU on a busy machine.
jest.setTimeout(30_000);

beforeEach(() => {
  jest.useFakeTimers();
  microphone.feed = Float32Array.from({ length: 40 * 48_000 }, (_, index) => Math.sin(index / 9) * ((index >> 13) % 4));
});
afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

test("opening a commentator syncs with the TV by itself, then says it's synced", async () => {
  const { result, fake } = await listening();
  expect(syncs(fake.paths())).toBe(1);
  expect(result.current.delay).toBe(20);
  expect(latestPlayer().seeks).toContain(-10); // straight to 20 s behind
  await advance(TICK_MS);
  expect(result.current.status).toMatchObject({ kind: "synced", label: "Synced with your TV" });
});

test("after a sync, the TV is re-checked every few minutes, with the commentary muted, not paused", async () => {
  const { result, fake } = await listening();
  await advance(AUTO_CHECK_INTERVAL_MS + 1_000); // into the check's listening
  expect(result.current.status.label).toBe("Checking your TV…");
  expect([latestPlayer().muted, latestPlayer().playing]).toEqual([true, true]);
  await advance(AUTO_LISTEN_SECONDS * 1_000);
  expect(syncs(fake.paths())).toBe(2);
  expect(latestPlayer().muted).toBe(false);
});

test("a sync that doesn't hear the TV says so and offers to try again; nothing checks by itself", async () => {
  const { result, fake } = await listening({ heard: false });
  expect(result.current.status).toMatchObject({ kind: "desynced", action: "sync" });
  const before = syncs(fake.paths());
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(before);
});

test("losing the connection and getting it back reloads the audio, then re-checks the TV", async () => {
  const { result, fake } = await listening();
  await act(() => setOnline(false));
  expect(result.current.status.label).toBe("Reconnecting…");
  Object.assign(latestPlayer(), { status: "error", keepsFailing: true });
  await advance(TICK_MS);
  latestPlayer().keepsFailing = false;
  await act(() => setOnline(true));
  expect(latestPlayer().reloads.length).toBeGreaterThan(0); // at once, not after a wait
  await advance(TICK_MS); // playing again
  expect(result.current.status.label).not.toBe("Reconnecting…");
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

test("sync off: nothing is checked, the delay is the listener's, and one tap turns it back on", async () => {
  const { result, fake } = await listening();
  await act(() => result.current.setIsSyncOn(false));
  expect(result.current.status).toMatchObject({ kind: "off", action: "turn-on" });
  await act(() => result.current.setBaseDelay(31.04));
  expect(result.current.delay).toBe(31);
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(1);
  await act(() => result.current.act("turn-on"));
  await advance(RECORDING_SECONDS * 1_000 + TICK_MS);
  expect(syncs(fake.paths())).toBe(2);
  expect(result.current.isSyncOn).toBe(true);
});

test("offline, the schedule waits for the connection", async () => {
  const { fake } = await listening();
  await act(() => setOnline(false));
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(1);
});

test("paused by the listener: says how far behind, never re-checks behind their back, and jumps straight back", async () => {
  const { result, fake } = await listening();
  await act(() => result.current.togglePause());
  expect(latestPlayer().playing).toBe(false);
  latestPlayer().advance(42);
  await advance(TICK_MS);
  expect(result.current.status).toMatchObject({ kind: "paused", label: "You're 0:42 behind · Jump back in", action: "jump" });
  await advance(AUTO_CHECK_INTERVAL_MS * 2);
  expect(syncs(fake.paths())).toBe(1);
  await act(() => result.current.act("jump"));
  expect(result.current.isPaused).toBe(false);
  await advance(TICK_MS);
  expect(latestPlayer().seeks.at(-1)).toBeGreaterThan(0); // forward, to the TV again
});

test("pausing twice plays again", async () => {
  const { result } = await listening();
  await act(() => result.current.togglePause());
  await act(() => result.current.togglePause());
  expect(result.current.isPaused).toBe(false);
});

test("the fine-tune adds to the synced delay, and the phone remembers it and the volume", async () => {
  const { result } = await listening();
  await act(() => result.current.setFineTune(0.3));
  expect(result.current.delay).toBe(20.3);
  expect(items.get(PREFERENCE_KEYS.fineTune)).toBe("0.3");
  await act(() => result.current.setVolume(0.6));
  expect(latestPlayer().volume).toBe(0.6);
  expect(items.get(PREFERENCE_KEYS.volume)).toBe("0.6");
  await act(() => result.current.setIsMuted(true));
  expect(latestPlayer().muted).toBe(true);
});

test("a remembered fine-tune and volume are used from the start", async () => {
  items.set(PREFERENCE_KEYS.fineTune, "-0.4");
  items.set(PREFERENCE_KEYS.volume, "0.5");
  const { result } = await listening();
  expect(result.current.delay).toBe(19.6);
  expect(latestPlayer().volume).toBe(0.5);
});

test("a refused microphone sends the listener to Settings", async () => {
  const open = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
  const { result } = await listening();
  await act(() => result.current.act("settings"));
  expect(open).toHaveBeenCalled();
});

test("resyncing by hand listens to the TV again", async () => {
  const { result, fake } = await listening();
  await act(() => result.current.act("sync"));
  await advance(RECORDING_SECONDS * 1_000 + TICK_MS);
  expect(syncs(fake.paths())).toBe(2);
});
