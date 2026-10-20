import { ANALYSIS_SAMPLE_RATE, extractFeatures } from "@commentary-sync/client/features";
import { SessionProvider } from "@commentary-sync/client/react";
import { resample } from "@commentary-sync/client/resample";
import { SYNC_MATCHED, SYNC_NOT_FOUND } from "@commentary-sync/client/testing";
import { act, renderHook } from "@testing-library/react-native";
import type { ReactNode } from "react";

import { useTvSync } from "@/hooks/useTvSync";
import { Session } from "@/lib/session";
import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { AUTO_LISTEN_SECONDS } from "@/lib/autoSync";
import { NOT_FOUND_RETRIES, RECORDING_SECONDS, RETRY_MS } from "@/lib/tvSync";
import { microphone, streams } from "../_fakeAudio";
import { items } from "../_fakeSecureStore";
import { listenerApi } from "../_render";

const SYNC = "/streams/s-1/sync";
const SERVER_NOW = 1_792_400_000;

/** What the TV sounds like: noise whose loudness changes, deterministic. */
function tv(seconds: number, rate: number): Float32Array {
  let state = 7;
  return Float32Array.from({ length: seconds * rate }, (_, index) => {
    state = (state * 1_103_515_245 + 12_345) % 2 ** 31;
    const loudness = 0.1 + 0.3 * Math.abs(Math.sin(index / 4_000));
    return loudness * (state / 2 ** 30 - 1);
  });
}

function signedIn({ children }: { children: ReactNode }) {
  return <SessionProvider createSession={() => new Session()}>{children}</SessionProvider>;
}

function api() {
  return listenerApi().on("GET", "/clock", { status: 200, body: { now: SERVER_NOW } });
}

/** Starts a sync (or an automatic check) and lets the listening run out. */
async function syncNow(onPlan = jest.fn(), { auto = false, currentDelay = 10 } = {}) {
  const hook = await renderHook(() => useTvSync("s-1", onPlan, currentDelay), { wrapper: signedIn });
  await act(async () => {
    void hook.result.current.start({ auto });
    await jest.advanceTimersByTimeAsync((auto ? AUTO_LISTEN_SECONDS : RECORDING_SECONDS) * 1_000);
  });
  await act(async () => {
    await jest.advanceTimersByTimeAsync(0);
  });
  return { ...hook, onPlan };
}

beforeEach(() => {
  jest.useFakeTimers();
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
  microphone.feed = tv(RECORDING_SECONDS, microphone.sampleRate);
});
afterEach(() => jest.useRealTimers());

test("only the features of what the phone heard are sent, never the sound, and the delay is set", async () => {
  const fake = api().on("POST", SYNC, { status: 200, body: SYNC_MATCHED });
  const { result, onPlan } = await syncNow();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(0);
  });
  expect(result.current.state).toMatchObject({ kind: "synced", auto: false, changed: true, delay: 23.5, pauseTv: 0 });
  expect(onPlan).toHaveBeenCalledWith({ delay: 23.5, pauseTv: 0 });
  const sent = fake.requests.find((request) => request.path.startsWith(SYNC))!;
  const expected = extractFeatures(resample(microphone.feed, 48_000, ANALYSIS_SAMPLE_RATE));
  expect(Array.from(sent.body as Float32Array)).toEqual(Array.from(expected.values));
  expect((sent.body as Float32Array).length).toBe(expected.frames * 16); // features, not samples
  expect(sent.contentType).toBe("application/octet-stream");
});

test("the capture is stamped in server time, from when the first sound arrived", async () => {
  microphone.firstTimestamp = 0.25;
  const fake = api().on("POST", SYNC, { status: 200, body: SYNC_MATCHED });
  await syncNow();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(0);
  });
  const sent = fake.requests.find((request) => request.path.startsWith(SYNC))!;
  const capturedAt = Number(new URL(`http://x${sent.path}`).searchParams.get("captured_at"));
  expect(capturedAt - SERVER_NOW).toBeGreaterThanOrEqual(0.25);
  expect(capturedAt - SERVER_NOW).toBeLessThan(1);
});

test("a stereo microphone is mixed to mono first", async () => {
  microphone.channels = 2;
  const fake = api().on("POST", SYNC, { status: 200, body: SYNC_MATCHED });
  await syncNow();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(0);
  });
  const sent = fake.requests.find((request) => request.path.startsWith(SYNC))!;
  const mono = extractFeatures(resample(microphone.feed, 48_000, ANALYSIS_SAMPLE_RATE));
  expect(Array.from(sent.body as Float32Array)).toEqual(Array.from(mono.values));
});

test("the microphone is on only while listening, and recording is switched off after", async () => {
  api().on("POST", SYNC, { status: 200, body: SYNC_MATCHED });
  await syncNow();
  expect([microphone.starts, microphone.stops]).toEqual([1, 1]);
  expect(microphone.modes).toEqual([{ allowsRecording: true, playsInSilentMode: true }, { allowsRecording: false }]);
});

test("says it is listening while it listens", async () => {
  api();
  const { result } = await renderHook(() => useTvSync("s-1", jest.fn(), 10), { wrapper: signedIn });
  await act(async () => {
    void result.current.start();
    await jest.advanceTimersByTimeAsync(1_000);
  });
  expect(result.current.state).toEqual({ kind: "recording", auto: false });
});

test("a TV ahead of the commentator's is retried until their TV catches up", async () => {
  const fake = api().on("POST", SYNC, { status: 200, body: SYNC_NOT_FOUND }, { status: 200, body: { ...SYNC_MATCHED, delay_seconds: -2 } });
  const { result } = await syncNow();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(RETRY_MS);
  });
  expect(result.current.state).toMatchObject({ kind: "synced", delay: 4, pauseTv: 6 });
  expect(fake.paths().filter((path) => path.startsWith(`POST ${SYNC}`))).toHaveLength(2);
});

test("never found, after the retries, says so", async () => {
  const fake = api().on("POST", SYNC, { status: 200, body: SYNC_NOT_FOUND });
  const { result, onPlan } = await syncNow();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(RETRY_MS * NOT_FOUND_RETRIES);
  });
  expect(result.current.state).toEqual({ kind: "not-found", auto: false, misses: 0 });
  expect(onPlan).not.toHaveBeenCalled();
  expect(fake.paths().filter((path) => path.startsWith(`POST ${SYNC}`))).toHaveLength(1 + NOT_FOUND_RETRIES);
});

test("a refused microphone is explained, and it never listens", async () => {
  api();
  microphone.granted = false;
  const { result } = await syncNow();
  expect(result.current.state).toEqual({ kind: "failed", auto: false, detail: expect.stringMatching(/Allow Commentary Sync to use the microphone/) });
  expect(microphone.starts).toBe(0);
});

test("a microphone that delivers nothing is a plain failure", async () => {
  api();
  microphone.feed = new Float32Array(0);
  const { result } = await syncNow();
  expect(result.current.state).toEqual({ kind: "failed", auto: false, detail: "Couldn't sync; try again." });
  expect(microphone.modes.at(-1)).toEqual({ allowsRecording: false });
});

test("the API's refusal is shown as it is", async () => {
  api().on("POST", SYNC, { status: 400, body: { detail: "features must cover 3 to 20 s" } });
  const { result } = await syncNow();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(0);
  });
  expect(result.current.state).toEqual({ kind: "failed", auto: false, detail: "features must cover 3 to 20 s" });
});

test("buffers outside a sync go nowhere", async () => {
  api();
  await renderHook(() => useTvSync("s-1", jest.fn(), 10), { wrapper: signedIn });
  await streams[0]!.start(); // delivers buffers with no sync running
  expect(microphone.starts).toBe(1);
});

test("leaving during a sync changes nothing afterwards (rule 71)", async () => {
  api().on("POST", SYNC, { status: 200, body: SYNC_MATCHED });
  const onPlan = jest.fn();
  const { result, unmount } = await renderHook(() => useTvSync("s-1", onPlan, 10), { wrapper: signedIn });
  await act(async () => {
    void result.current.start();
  });
  await unmount();
  await jest.advanceTimersByTimeAsync(RECORDING_SECONDS * 1_000 + 100);
  expect(onPlan).not.toHaveBeenCalled();
});


describe("automatic re-checks", () => {
  test("listen for less time, and leave an unchanged delay alone", async () => {
    const fake = api().on("POST", SYNC, { status: 200, body: { ...SYNC_MATCHED, delay_seconds: 20.2 } });
    const { result, onPlan } = await syncNow(jest.fn(), { auto: true, currentDelay: 20 });
    expect(result.current.state).toMatchObject({ kind: "synced", auto: true, changed: false, delay: 20 });
    expect(onPlan).not.toHaveBeenCalled();
    const sent = fake.requests.find((request) => request.path.startsWith(SYNC))!;
    const frames = (sent.body as Float32Array).length / 16;
    expect(frames).toBeLessThan(AUTO_LISTEN_SECONDS * 100); // about 6 s of features, not 10
  });

  test("a TV that moved moves the delay", async () => {
    api().on("POST", SYNC, { status: 200, body: { ...SYNC_MATCHED, delay_seconds: 27 } });
    const { result, onPlan } = await syncNow(jest.fn(), { auto: true, currentDelay: 20 });
    expect(result.current.state).toMatchObject({ kind: "synced", auto: true, changed: true, delay: 27 });
    expect(onPlan).toHaveBeenCalledWith({ delay: 27, pauseTv: 0 });
  });

  test("misses in a row are counted, and a match resets the count", async () => {
    api().on("POST", SYNC, { status: 200, body: SYNC_NOT_FOUND });
    const onPlan = jest.fn();
    const { result } = await renderHook(() => useTvSync("s-1", onPlan, 20), { wrapper: signedIn });
    const check = () =>
      act(async () => {
        void result.current.start({ auto: true });
        await jest.advanceTimersByTimeAsync(AUTO_LISTEN_SECONDS * 1_000 + RETRY_MS * NOT_FOUND_RETRIES);
      });
    await check();
    await check();
    expect(result.current.state).toEqual({ kind: "not-found", auto: true, misses: 2 });
    await act(async () => {
      void result.current.start();
      await jest.advanceTimersByTimeAsync(RECORDING_SECONDS * 1_000 + RETRY_MS * NOT_FOUND_RETRIES);
    });
    expect(result.current.state).toEqual({ kind: "not-found", auto: false, misses: 0 });
  });
});
