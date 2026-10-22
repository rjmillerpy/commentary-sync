import type { Page } from "@playwright/test";

// The fake microphone always plays the same file. To stand in for a
// commentator who talks, then pauses with only the TV playing, the studio's
// broadcast microphone (the one opened with echo cancellation; the raw one
// that records the room for TV sync is left alone) is passed through a gain
// the test turns down to TV_VOLUME, "the TV across the room", and back up to
// VOICE_VOLUME, "talking into the mic".

export const VOICE_VOLUME = 1;
export const TV_VOLUME = 0.03; // about 30 dB below the voice

declare global {
  interface Window {
    setRoomVolume(volume: number): void;
  }
}

function installRoomVolume(): void {
  const gains: GainNode[] = [];
  const open = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  window.setRoomVolume = (volume) => gains.forEach((gain) => (gain.gain.value = volume));
  navigator.mediaDevices.getUserMedia = async (constraints) => {
    const stream = await open(constraints);
    const audio = constraints?.audio;
    if (typeof audio !== "object" || audio.echoCancellation !== true) return stream;
    const context = new AudioContext();
    const gain = context.createGain();
    const out = context.createMediaStreamDestination();
    context.createMediaStreamSource(stream).connect(gain).connect(out);
    gains.push(gain);
    return out.stream;
  };
}

/** Before the studio loads: its microphone gets a volume the test controls. */
export async function controlRoomVolume(page: Page): Promise<void> {
  await page.addInitScript(installRoomVolume);
}

export async function setRoomVolume(page: Page, volume: number): Promise<void> {
  await page.evaluate((value) => window.setRoomVolume(value), volume);
}
