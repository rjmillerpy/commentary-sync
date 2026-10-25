/** The browser's microphones and Web Audio, faked at the device boundary. */

export class FakeTrack {
  readonly kind = "audio";
  readonly stop = jest.fn();
  constructor(readonly deviceId: string) {}
}

export class FakeStream {
  readonly track: FakeTrack;
  constructor(deviceId: string) {
    this.track = new FakeTrack(deviceId);
  }
  getTracks(): FakeTrack[] {
    return [this.track];
  }
  getAudioTracks(): FakeTrack[] {
    return [this.track];
  }
}

export const MICROPHONES = [
  { kind: "audioinput", deviceId: "default", label: "Default", groupId: "g" },
  { kind: "audioinput", deviceId: "usb-mic", label: "USB Microphone", groupId: "g" },
  { kind: "audiooutput", deviceId: "speakers", label: "Speakers", groupId: "g" },
];

export interface FakeMedia {
  opened: FakeStream[];
  constraints: MediaStreamConstraints[];
  /** A DOMException name to fail the next getUserMedia with, or null. */
  failure: string | null;
  /** The byte the analyser fills each sample with: 128 is silence. */
  sampleByte: number;
  contexts: { closed: boolean; sampleRate: number; startedAt: number }[];
  /** Every AudioWorkletNode made, newest last: a test plays audio into it with `deliver`. */
  worklets: FakeWorkletNode[];
  /** A name to make audioWorklet.addModule fail with, or null. */
  workletFailure: string | null;
}

/** An AudioWorkletNode: the processor's messages are delivered by the test. */
export class FakeWorkletNode {
  readonly port: { onmessage: ((event: MessageEvent) => void) | null } = { onmessage: null };
  constructor(
    readonly context: unknown,
    readonly name: string,
    readonly options: AudioWorkletNodeOptions,
  ) {}
  /** What the processor posts: `samples` starting at context frame `frame`. */
  deliver(frame: number, samples: Float32Array): void {
    this.port.onmessage?.({ data: { frame, samples } } as MessageEvent);
  }
}

export function installMedia(): FakeMedia {
  const media: FakeMedia = {
    opened: [],
    constraints: [],
    failure: null,
    sampleByte: 128,
    contexts: [],
    worklets: [],
    workletFailure: null,
  };
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: jest.fn(async (constraints: MediaStreamConstraints) => {
        media.constraints.push(constraints);
        if (media.failure !== null) throw new DOMException("refused", media.failure);
        const audio = constraints.audio as MediaTrackConstraints;
        const deviceId = (audio.deviceId as { exact: string } | undefined)?.exact ?? "default";
        const stream = new FakeStream(deviceId);
        media.opened.push(stream);
        return stream;
      }),
      enumerateDevices: jest.fn(async () => MICROPHONES),
    },
  });
  class FakeAudioContext {
    closed = false;
    readonly sampleRate: number;
    readonly audioWorklet = {
      addModule: jest.fn(async () => {
        if (media.workletFailure !== null) throw new DOMException("refused", media.workletFailure);
      }),
    };
    /** When the context started, as device time (epoch seconds). */
    readonly startedAt: number;
    private readonly startedPerformance = performance.now();
    constructor(options: AudioContextOptions = {}) {
      this.sampleRate = options.sampleRate ?? 48_000;
      this.startedAt = (performance.timeOrigin + this.startedPerformance) / 1_000;
      media.contexts.push(this);
    }
    /** Context time 0 is the moment the context was made. */
    getOutputTimestamp(): AudioTimestamp {
      return { contextTime: 0, performanceTime: this.startedPerformance };
    }
    createAnalyser() {
      return {
        fftSize: 0,
        getByteTimeDomainData: (samples: Uint8Array) => samples.fill(media.sampleByte),
      };
    }
    createMediaStreamSource() {
      return { connect: jest.fn(), disconnect: jest.fn() };
    }
    async close() {
      this.closed = true;
    }
  }
  Object.defineProperty(globalThis, "AudioContext", { configurable: true, value: FakeAudioContext });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: class extends FakeWorkletNode {
      constructor(context: unknown, name: string, options: AudioWorkletNodeOptions) {
        super(context, name, options);
        media.worklets.push(this);
      }
    },
  });
  // jsdom has no object URLs; the worklet's module is one.
  Object.assign(URL, { createObjectURL: jest.fn(() => "blob:worklet"), revokeObjectURL: jest.fn() });
  return media;
}
