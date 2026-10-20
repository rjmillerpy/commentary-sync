/** The commentator's room, recorded for listeners to sync their TVs against.
 *
 * While live, the studio opens the microphone a second time with echo
 * cancellation, noise suppression and auto gain off, so the TV in the
 * background survives (the broadcast keeps its own cleaned-up track). An
 * AudioWorklet hands the audio over at 8 kHz, the matcher's rate, and it is
 * sent to the API in 5-second chunks of 16-bit PCM, each stamped with the
 * time its first sample was captured. It is never broadcast. */

export const REFERENCE_SAMPLE_RATE = 8_000;
export const CHUNK_SECONDS = 5;
export const ROOM_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
};
const PROCESSOR_NAME = "reference-capture";
const INT16_MAX = 0x7fff;
const MILLISECONDS_PER_SECOND = 1_000;

// Runs on the audio thread: posts each block of samples with the frame
// number it starts at.
const WORKLET_SOURCE = `
class ReferenceCapture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage({ frame: currentFrame, samples: channel.slice() });
    return true;
  }
}
registerProcessor("${PROCESSOR_NAME}", ReferenceCapture);
`;

export interface ReferenceChunk {
  pcm: Int16Array;
  /** When the first sample was captured, by this device's clock (epoch seconds). */
  capturedAt: number;
}

/** Collects blocks of samples into fixed-size chunks of 16-bit PCM. */
export class Chunker {
  private readonly buffer: Float32Array;
  private filled = 0;
  private startedAt = 0;

  constructor(
    private readonly size: number,
    private readonly sampleRate: number,
    private readonly onChunk: (chunk: ReferenceChunk) => void,
  ) {
    this.buffer = new Float32Array(size);
  }

  /** `samples` whose first one was captured at `capturedAt`. */
  add(samples: Float32Array, capturedAt: number): void {
    let used = 0;
    while (used < samples.length) {
      if (this.filled === 0) this.startedAt = capturedAt + used / this.sampleRate;
      const taken = Math.min(samples.length - used, this.size - this.filled);
      this.buffer.set(samples.subarray(used, used + taken), this.filled);
      this.filled += taken;
      used += taken;
      if (this.filled === this.size) this.flush();
    }
  }

  private flush(): void {
    this.onChunk({ pcm: toPcm(this.buffer), capturedAt: this.startedAt });
    this.filled = 0;
  }
}

export function toPcm(samples: Float32Array): Int16Array {
  return Int16Array.from(samples, (sample) => Math.round(Math.max(-1, Math.min(1, sample)) * INT16_MAX));
}

/** Records `stream` in chunks until the returned function is called. */
export async function recordRoom(stream: MediaStream, onChunk: (chunk: ReferenceChunk) => void): Promise<() => void> {
  // The context runs at 8 kHz: the browser resamples the microphone for us.
  const context = new AudioContext({ sampleRate: REFERENCE_SAMPLE_RATE });
  const moduleUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "text/javascript" }));
  try {
    await context.audioWorklet.addModule(moduleUrl);
  } finally {
    URL.revokeObjectURL(moduleUrl);
  }
  const source = context.createMediaStreamSource(stream);
  // No outputs: a sink, which the browser runs without it reaching the speakers.
  const capture = new AudioWorkletNode(context, PROCESSOR_NAME, { numberOfInputs: 1, numberOfOutputs: 0 });
  const chunker = new Chunker(CHUNK_SECONDS * REFERENCE_SAMPLE_RATE, REFERENCE_SAMPLE_RATE, onChunk);
  capture.port.onmessage = (event: MessageEvent<{ frame: number; samples: Float32Array }>) => {
    chunker.add(event.data.samples, captureTime(context, event.data.frame));
  };
  source.connect(capture);
  return () => {
    capture.port.onmessage = null;
    source.disconnect();
    void context.close();
  };
}

/** The device time (epoch seconds) at which `frame` of the context was captured. */
function captureTime(context: AudioContext, frame: number): number {
  const { contextTime = 0, performanceTime = 0 } = context.getOutputTimestamp();
  const frameTime = frame / context.sampleRate;
  return (performance.timeOrigin + performanceTime) / MILLISECONDS_PER_SECOND + (frameTime - contextTime);
}
