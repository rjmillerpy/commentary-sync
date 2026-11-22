/** A number in React state that the phone remembers (lib/preferences.ts). */

import { useCallback, useState } from "react";

import { type PreferenceKey, readNumber, writeNumber } from "@/lib/preferences";

export function useStoredNumber(key: PreferenceKey, fallback: number, clamp: (value: number) => number) {
  const [value, setValue] = useState(() => readNumber(key, fallback, clamp));
  const set = useCallback(
    (next: number) => {
      const clamped = clamp(next);
      setValue(clamped);
      writeNumber(key, clamped);
    },
    [key, clamp],
  );
  return [value, set] as const;
}
