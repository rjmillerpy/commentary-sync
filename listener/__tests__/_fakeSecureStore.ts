/** expo-secure-store, in memory: the phone's Keychain/Keystore is a boundary. */

export const items = new Map<string, string>();
/** Make every call throw, as on a device whose secure storage is unavailable. */
export const failure = { enabled: false };

function check(): void {
  if (failure.enabled) throw new Error("secure storage unavailable");
}

export function getItem(key: string): string | null {
  check();
  return items.get(key) ?? null;
}

export function setItem(key: string, value: string): void {
  check();
  items.set(key, value);
}

export async function deleteItemAsync(key: string): Promise<void> {
  check();
  items.delete(key);
}

export function reset(): void {
  items.clear();
  failure.enabled = false;
}
