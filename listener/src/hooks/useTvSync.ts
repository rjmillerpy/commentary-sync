/** "Sync with my TV": listen to the TV for a few seconds, turn what the
 * phone heard into the matcher's features right here (client/src/features.ts),
 * have the API find that moment in the commentator's room audio, and set the
 * delay from it (lib/tvSync.ts). The sound itself never leaves the phone and
 * is kept nowhere: only the features are sent.
 *
 * `start({ auto: true })` is an automatic re-check (lib/autoSync.ts): it
 * listens for less time, and changes the delay only if the TV moved. */

import { ApiError } from "@commentary-sync/client/api";
import { measureClockOffset } from "@commentary-sync/client/clock";
import { ANALYSIS_SAMPLE_RATE, extractFeatures, type Features } from "@commentary-sync/client/features";
import { useSession } from "@commentary-sync/client/react";
import { resample } from "@commentary-sync/client/resample";
import type { SyncResult } from "@commentary-sync/client/schema";
import {
  type AudioStream,
  type AudioStreamBuffer,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioStream,
} from "expo-audio";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { AUTO_LISTEN_SECONDS, judgeRecheck } from "@/lib/autoSync";
import { type DelayPlan, NOT_FOUND_RETRIES, planDelay, RECORDING_SECONDS, RETRY_MS } from "@/lib/tvSync";

/** `auto`: started by the app (an automatic re-check), not by the listener. */
export type TvSyncState =
  | { kind: "idle" }
  | { kind: "recording"; auto: boolean }
  | { kind: "matching"; auto: boolean }
  | ({ kind: "synced"; auto: boolean; changed: boolean; at: number } & DelayPlan)
  | { kind: "not-found"; auto: boolean; misses: number }
  | { kind: "failed"; auto: boolean; detail: string };

export interface SyncOptions {
  auto?: boolean;
}

type BufferListener = (buffer: AudioStreamBuffer) => void;

const MILLISECONDS_PER_SECOND = 1_000;
const NO_MICROPHONE = "Allow Commentary Sync to use the microphone in Settings, then try again.";
const FAILED = "Couldn't sync; try again.";
const nowSeconds = () => Date.now() / MILLISECONDS_PER_SECOND;
const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** The listener said no to the microphone. */
class MicrophoneDeniedError extends Error {}

export function useTvSync(streamId: string, onPlan: (plan: DelayPlan) => void, currentDelay: number) {
  const { authorized } = useSession();
  const delayNow = useRef(currentDelay);
  useEffect(() => {
    delayNow.current = currentDelay;
  }, [currentDelay]);
  const misses = useRef(0); // automatic checks in a row that didn't hear the TV
  // Buffers go to whoever is listening now: nobody, outside a sync.
  const listener = useRef<BufferListener | null>(null);
  const { stream } = useAudioStream({
    sampleRate: ANALYSIS_SAMPLE_RATE, // a request: phones may deliver their own rate
    channels: 1,
    encoding: "float32",
    onBuffer: (buffer) => listener.current?.(buffer),
  });
  const [state, setState] = useState<TvSyncState>({ kind: "idle" });
  const isMounted = useRef(true);
  useEffect(() => () => void (isMounted.current = false), []);

  const start = useCallback(
    async ({ auto = false }: SyncOptions = {}) => {
      const show = (next: TvSyncState) => isMounted.current && setState(next);
      show({ kind: "recording", auto });
      try {
        const seconds = auto ? AUTO_LISTEN_SECONDS : RECORDING_SECONDS;
        const { features, capturedAt } = await listenToTv(stream, listener, seconds);
        show({ kind: "matching", auto });
        const send = () => authorized((token) => api.syncToTv(token, streamId, features, capturedAt));
        const result = await matchWithRetries(send);
        if (result.status === "not_found") {
          misses.current = auto ? misses.current + 1 : 0;
          return show({ kind: "not-found", auto, misses: misses.current });
        }
        misses.current = 0;
        const plan = planDelay(result.delay_seconds);
        const changed = !auto || judgeRecheck(plan, delayNow.current).kind === "adjust";
        if (changed && isMounted.current) onPlan(plan);
        show({ kind: "synced", auto, changed, at: Date.now(), ...plan });
      } catch (failure) {
        show({ kind: "failed", auto, detail: describe(failure) });
      }
    },
    [authorized, onPlan, stream, streamId],
  );

  return { state, start };
}

/** Listens for `seconds`; returns the features of what was heard and when it
 * started, in server time. */
async function listenToTv(
  stream: AudioStream,
  listener: { current: BufferListener | null },
  seconds: number,
): Promise<{ features: Features; capturedAt: number }> {
  if (!(await requestRecordingPermissionsAsync()).granted) throw new MicrophoneDeniedError();
  const offset = await measureClockOffset(api.serverTime, nowSeconds);
  const heard = new Heard();
  await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
  try {
    listener.current = (buffer) => heard.add(buffer);
    const startedAt = nowSeconds();
    await stream.start();
    await wait(seconds * MILLISECONDS_PER_SECOND);
    stream.stop();
    const samples = resample(heard.samples(), heard.sampleRate, ANALYSIS_SAMPLE_RATE);
    // The first buffer's timestamp is how far into the stream it began.
    return { features: extractFeatures(samples), capturedAt: startedAt + heard.firstTimestamp + offset };
  } finally {
    listener.current = null;
    await setAudioModeAsync({ allowsRecording: false });
  }
}

/** The microphone's buffers, gathered and mixed down to mono. */
class Heard {
  private readonly chunks: Float32Array[] = [];
  sampleRate = ANALYSIS_SAMPLE_RATE;
  firstTimestamp = 0;

  add({ data, sampleRate, channels, timestamp }: AudioStreamBuffer): void {
    if (this.chunks.length === 0) this.firstTimestamp = timestamp;
    this.sampleRate = sampleRate;
    const interleaved = new Float32Array(data);
    const mono = new Float32Array(interleaved.length / channels);
    for (let frame = 0; frame < mono.length; frame += 1) {
      let sum = 0;
      for (let channel = 0; channel < channels; channel += 1) sum += interleaved[frame * channels + channel]!;
      mono[frame] = sum / channels;
    }
    this.chunks.push(mono);
  }

  samples(): Float32Array {
    if (this.chunks.length === 0) throw new Error("the microphone delivered nothing");
    const all = new Float32Array(this.chunks.reduce((total, chunk) => total + chunk.length, 0));
    let at = 0;
    for (const chunk of this.chunks) {
      all.set(chunk, at);
      at += chunk.length;
    }
    return all;
  }
}

async function matchWithRetries(send: () => Promise<SyncResult>): Promise<SyncResult> {
  let result = await send();
  for (let retry = 0; retry < NOT_FOUND_RETRIES && result.status === "not_found"; retry += 1) {
    await wait(RETRY_MS);
    result = await send();
  }
  return result;
}

function describe(failure: unknown): string {
  if (failure instanceof MicrophoneDeniedError) return NO_MICROPHONE;
  return failure instanceof ApiError ? failure.detail : FAILED;
}
