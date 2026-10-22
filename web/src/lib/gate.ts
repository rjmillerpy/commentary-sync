/** The broadcast's voice gate: listeners hear the commentator's microphone
 * only while the commentator is talking.
 *
 * A commentator's microphone also hears their TV, and rebroadcasting the
 * game's sound is the main legal risk. The browser's echo cancellation and
 * noise suppression don't remove it: the TV is not the browser's own output,
 * and its announcers are speech. But the commentator sits close to the
 * microphone and the TV doesn't, so their voice is much louder there. The
 * gate passes sound above a threshold set by the TV check (lib/tvCheck.ts),
 * a little above the TV's loudest, and is silent below it. It runs on the
 * audio thread (an AudioWorklet, public/voice-gate.js), with a short
 * look-ahead so the first syllable isn't cut off, and a hold so it doesn't
 * close between words. Until a threshold is set it lets nothing through. */

export interface GateTiming {
  /** How quickly the measured loudness follows the sound. */
  smoothingSeconds: number;
  /** How long the gate stays open after the sound drops below the threshold. */
  holdSeconds: number;
  attackSeconds: number;
  releaseSeconds: number;
  /** How far the audio is delayed, so the gate opens just before a word. */
  lookaheadSeconds: number;
  /** How often the gate reports the microphone's loudness. */
  reportSeconds: number;
}

export const GATE_TIMING: GateTiming = {
  smoothingSeconds: 0.01,
  holdSeconds: 0.25,
  attackSeconds: 0.005,
  releaseSeconds: 0.08,
  lookaheadSeconds: 0.02,
  reportSeconds: 0.05,
};

/** One report period, as the audio thread measures it: the microphone's mean
 * square before the gate, and the share of samples the gate let through. */
export interface GateReport {
  power: number;
  openShare: number;
}

/** A report in decibels (dBFS): what the TV check and the live watch use. */
export interface GateLevels {
  levelDb: number;
  openShare: number;
}

export const SILENCE_DB = -100;
const DECIBELS_PER_POWER_DECADE = 10;
/** The audio-thread half, served as is from public/ (never bundled). */
export const GATE_MODULE_URL = "/voice-gate.js";
const PROCESSOR_NAME = "voice-gate";

export function toDecibels(power: number): number {
  return power > 0 ? Math.max(SILENCE_DB, DECIBELS_PER_POWER_DECADE * Math.log10(power)) : SILENCE_DB;
}

export function toPower(decibels: number): number {
  return DECIBELS_PER_POWER_DECADE ** (decibels / DECIBELS_PER_POWER_DECADE);
}

export interface Gate {
  /** The gated microphone: what goes on air. */
  track: MediaStreamTrack;
  setThreshold(decibels: number): void;
  close(): void;
}

/** Gates `microphone`; `onLevels` hears every report until `close`. */
export async function openGate(microphone: MediaStream, onLevels: (levels: GateLevels) => void): Promise<Gate> {
  const context = new AudioContext();
  try {
    await context.audioWorklet.addModule(GATE_MODULE_URL);
  } catch (error) {
    void context.close();
    throw error;
  }
  const source = context.createMediaStreamSource(microphone);
  const gate = new AudioWorkletNode(context, PROCESSOR_NAME, {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    processorOptions: GATE_TIMING,
  });
  const onAir = context.createMediaStreamDestination();
  gate.port.onmessage = ({ data }: MessageEvent<GateReport>) => {
    onLevels({ levelDb: toDecibels(data.power), openShare: data.openShare });
  };
  source.connect(gate);
  gate.connect(onAir);
  const [track] = onAir.stream.getAudioTracks();
  return {
    track: track!,
    setThreshold: (decibels) => gate.port.postMessage(toPower(decibels)),
    close() {
      gate.port.onmessage = null;
      source.disconnect();
      track?.stop();
      void context.close();
    },
  };
}
