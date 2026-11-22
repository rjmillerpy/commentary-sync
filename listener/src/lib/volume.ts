/** The commentary's volume (UI rule 4): ten steps, and its own mute. The
 * TV's volume is the TV remote's; the app never touches it. */

export const VOLUME_STEP = 0.1;
export const VOLUME_STEPS = 10;
export const DEFAULT_VOLUME = 1;

export function clampVolume(volume: number): number {
  return Math.min(1, Math.max(0, Math.round(volume * VOLUME_STEPS) / VOLUME_STEPS));
}
