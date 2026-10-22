/** The browser's microphones: listing them, opening one, and how loud it is. */

// Speech cleanup on: commentators talk over a TV, often without headphones.
// Auto gain off: it turns the TV up whenever the commentator pauses, which
// is exactly when the voice gate (lib/gate.ts) needs it quiet.
export const MICROPHONE_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: false,
};

const ANALYSER_FFT_SIZE = 1024;
const SAMPLE_MIDPOINT = 128; // byte time-domain samples are centred here
const LEVEL_GAIN = 4; // speech RMS is around 0.05-0.25; this fills the meter
const LEVEL_INTERVAL_MS = 100;

// Browsers offer microphones only to pages on a secure connection (https, or
// localhost); elsewhere navigator.mediaDevices is missing.
const INSECURE_CONTEXT = "InsecureContextError";

const FAILURE_MESSAGES: Record<string, string> = {
  [INSECURE_CONTEXT]: "The microphone only works over a secure (https) connection.",
  NotAllowedError: "Microphone access is blocked. Allow it in the browser's site settings.",
  NotFoundError: "No microphone found. Plug one in and try again.",
  NotReadableError: "The microphone is in use by another app.",
};
const UNKNOWN_FAILURE = "Couldn't open the microphone.";

export function microphoneFailure(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  return FAILURE_MESSAGES[name] ?? UNKNOWN_FAILURE;
}

/** Microphones, labelled once the user has allowed access to one. */
export async function listMicrophones(): Promise<MediaDeviceInfo[]> {
  const devices = await mediaDevices().enumerateDevices();
  return devices.filter((device) => device.kind === "audioinput");
}

// Async, so every failure, a missing mediaDevices included, is a rejection
// the caller's catch sees, never a throw that escapes it.
export async function openMicrophone(
  deviceId: string | null,
  constraints: MediaTrackConstraints = MICROPHONE_CONSTRAINTS,
): Promise<MediaStream> {
  const audio = deviceId === null ? constraints : { ...constraints, deviceId: { exact: deviceId } };
  return mediaDevices().getUserMedia({ audio, video: false });
}

function mediaDevices(): MediaDevices {
  const devices = navigator.mediaDevices as MediaDevices | undefined;
  if (devices === undefined) {
    const error = new Error("navigator.mediaDevices is missing: not a secure context");
    error.name = INSECURE_CONTEXT;
    throw error;
  }
  return devices;
}

export function closeMicrophone(stream: MediaStream): void {
  stream.getTracks().forEach((track) => track.stop());
}

/** Calls `onLevel` with the loudness (0 to 1) every 100 ms until the
 * returned function is called. */
export function watchLevel(stream: MediaStream, onLevel: (level: number) => void): () => void {
  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = ANALYSER_FFT_SIZE;
  const source = context.createMediaStreamSource(stream);
  source.connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);
  const timer = setInterval(() => {
    analyser.getByteTimeDomainData(samples);
    onLevel(levelOf(samples));
  }, LEVEL_INTERVAL_MS);
  return () => {
    clearInterval(timer);
    source.disconnect();
    void context.close();
  };
}

/** RMS of byte samples, scaled to fill a meter at normal speaking volume. */
export function levelOf(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let sumOfSquares = 0;
  for (const sample of samples) {
    const centred = (sample - SAMPLE_MIDPOINT) / SAMPLE_MIDPOINT;
    sumOfSquares += centred * centred;
  }
  return Math.min(1, Math.sqrt(sumOfSquares / samples.length) * LEVEL_GAIN);
}
