import { PREFERENCE_KEYS, readFlag, readNumber, writeFlag, writeNumber } from "@/lib/preferences";
import { failure, items } from "../_fakeSecureStore";

const KEY = PREFERENCE_KEYS.fineTune;
const half = (value: number) => Math.min(5, value);

test("a number is written and read back, through its clamp", () => {
  writeNumber(KEY, 0.3);
  expect(readNumber(KEY, 0, half)).toBe(0.3);
  writeNumber(KEY, 9);
  expect(readNumber(KEY, 0, half)).toBe(5);
});

test.each([
  ["nothing stored", null],
  ["not a number", "loud"],
  ["not finite", "Infinity"],
])("%s reads as the default (rule 5)", (_case, stored) => {
  if (stored !== null) items.set(KEY, stored);
  expect(readNumber(KEY, 1.5, half)).toBe(1.5);
});

test("a flag is unset until written", () => {
  expect(readFlag(PREFERENCE_KEYS.syncTipSeen)).toBe(false);
  writeFlag(PREFERENCE_KEYS.syncTipSeen);
  expect(readFlag(PREFERENCE_KEYS.syncTipSeen)).toBe(true);
});

test("with storage unavailable, reads give defaults and writes don't throw", () => {
  failure.enabled = true;
  expect(() => writeNumber(KEY, 1)).not.toThrow();
  expect(readNumber(KEY, 2, half)).toBe(2);
  expect(readFlag(PREFERENCE_KEYS.syncTipSeen)).toBe(false);
});
