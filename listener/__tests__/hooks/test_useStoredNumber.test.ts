import { act, renderHook } from "@testing-library/react-native";

import { useStoredNumber } from "@/hooks/useStoredNumber";
import { PREFERENCE_KEYS } from "@/lib/preferences";
import { items } from "../_fakeSecureStore";

const atMostTwo = (value: number) => Math.min(2, value);

test("starts from what the phone remembered, or the default", async () => {
  const { result } = await renderHook(() => useStoredNumber(PREFERENCE_KEYS.volume, 1, atMostTwo));
  expect(result.current[0]).toBe(1);
  items.set(PREFERENCE_KEYS.volume, "0.5");
  const { result: remembered } = await renderHook(() => useStoredNumber(PREFERENCE_KEYS.volume, 1, atMostTwo));
  expect(remembered.current[0]).toBe(0.5);
});

test("a new value is clamped, kept and remembered", async () => {
  const { result } = await renderHook(() => useStoredNumber(PREFERENCE_KEYS.volume, 1, atMostTwo));
  await act(() => result.current[1](5));
  expect(result.current[0]).toBe(2);
  expect(items.get(PREFERENCE_KEYS.volume)).toBe("2");
});
