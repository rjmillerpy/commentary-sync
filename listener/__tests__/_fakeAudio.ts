/** expo-audio, faked: the phone's microphone is a boundary. While a stream
 * runs, the fake delivers `microphone.feed` (what the TV sounds like) in
 * one-second buffers, one each second as a phone would (the first at once),
 * at `microphone.sampleRate` and `microphone.channels`, until stopped. */

import type { AudioStreamBuffer, AudioStreamOptions } from "expo-audio";

export const microphone = {
  granted: true,
  modes: [] as object[],
  sampleRate: 48_000,
  channels: 1,
  feed: new Float32Array(0) as Float32Array,
  /** Seconds into the stream that the first buffer arrives. */
  firstTimestamp: 0.05,
  starts: 0,
  stops: 0,
};

const SECOND_MS = 1_000;

export class FakeAudioStream {
  isStreaming = false;
  private timer: ReturnType<typeof setInterval> | undefined;
  constructor(private readonly options: AudioStreamOptions) {}

  async start(): Promise<void> {
    this.isStreaming = true;
    microphone.starts += 1;
    let second = 0;
    const deliver = () => {
      if (!this.deliverSecond(second)) clearInterval(this.timer);
      second += 1;
    };
    deliver();
    this.timer = setInterval(deliver, SECOND_MS);
  }

  stop(): void {
    this.isStreaming = false;
    clearInterval(this.timer);
    microphone.stops += 1;
  }

  /** One second of the feed; false once the feed has run out. */
  private deliverSecond(second: number): boolean {
    const { sampleRate, channels, feed } = microphone;
    const start = second * sampleRate;
    if (start >= feed.length) return false;
    const mono = feed.subarray(start, start + sampleRate);
    const interleaved = new Float32Array(mono.length * channels);
    mono.forEach((sample, frame) => interleaved.fill(sample, frame * channels, (frame + 1) * channels));
    const buffer: AudioStreamBuffer = {
      data: interleaved.buffer,
      sampleRate,
      channels,
      timestamp: microphone.firstTimestamp + second,
    };
    this.options.onBuffer?.(buffer);
    return true;
  }
}

export const streams: FakeAudioStream[] = [];

export function useAudioStream(options: AudioStreamOptions = {}) {
  const { useState } = jest.requireActual<typeof import("react")>("react");
  const [stream] = useState(() => {
    const made = new FakeAudioStream(options);
    streams.push(made);
    return made;
  });
  return { stream, isStreaming: stream.isStreaming };
}

export async function requestRecordingPermissionsAsync() {
  return { granted: microphone.granted, status: microphone.granted ? "granted" : "denied" };
}

export async function setAudioModeAsync(mode: object): Promise<void> {
  microphone.modes.push(mode);
}

export function reset(): void {
  streams.length = 0;
  Object.assign(microphone, {
    granted: true,
    sampleRate: 48_000,
    channels: 1,
    feed: new Float32Array(0),
    firstTimestamp: 0.05,
    starts: 0,
    stops: 0,
  });
  microphone.modes.length = 0;
}
