/** What the app remembers on this phone between listens (UI rule 1.4,
 * 4): the listener's fine-tune, the commentary volume, and whether they've
 * seen the sync status explained. In the phone's secure storage (Keychain,
 * Keystore), the one store the app already has; nothing here is secret, but
 * it's small and needs no new native module. Read back like any outside
 * input (rule 5): anything unreadable or out of range is the default. */

import * as SecureStore from "expo-secure-store";

export const PREFERENCE_KEYS = {
  fineTune: "commentary-sync.fine-tune-seconds",
  volume: "commentary-sync.volume",
  syncTipSeen: "commentary-sync.sync-tip-seen",
} as const;

export type PreferenceKey = (typeof PREFERENCE_KEYS)[keyof typeof PREFERENCE_KEYS];

const SEEN = "1";

/** The stored number, put through `clamp`; `fallback` if missing or not a number. */
export function readNumber(key: PreferenceKey, fallback: number, clamp: (value: number) => number): number {
  const stored = read(key);
  const value = stored === null ? Number.NaN : Number(stored);
  return Number.isFinite(value) ? clamp(value) : fallback;
}

export function writeNumber(key: PreferenceKey, value: number): void {
  write(key, String(value));
}

export function readFlag(key: PreferenceKey): boolean {
  return read(key) === SEEN;
}

export function writeFlag(key: PreferenceKey): void {
  write(key, SEEN);
}

function read(key: PreferenceKey): string | null {
  try {
    return SecureStore.getItem(key);
  } catch {
    return null; // storage unavailable: the defaults, every time
  }
}

function write(key: PreferenceKey, value: string): void {
  try {
    SecureStore.setItem(key, value);
  } catch {
    // storage unavailable: remembered until the app closes, in React state
  }
}
