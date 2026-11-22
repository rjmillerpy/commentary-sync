import {
  clampDelay,
  clampFineTune,
  correction,
  DELAY_NUDGES,
  formatBehind,
  formatOffset,
  formatSeconds,
  NO_SEEKS,
  nextHistory,
  SEEK_COOLDOWN_MS,
  type SeekHistory,
} from "@/lib/delay";

const TARGET = 10;
const NOW = 1_000_000;
const reading = (offset: number | null, position = 60, isHolding = false) => ({ offset, position, isHolding });

test.each([
  ["the player doesn't know its offset yet", reading(null), { kind: "none" }],
  ["on target", reading(10), { kind: "none" }],
  ["within ±0.25 s", reading(10.2), { kind: "none" }],
  ["a little too close to live: play 5% slower", reading(9.6), { kind: "rate", rate: expect.closeTo(0.95, 6) }],
  ["a little too far behind: play 5% faster", reading(10.6), { kind: "rate", rate: expect.closeTo(1.05, 6) }],
  ["up to 2 s off: still by speed", reading(8.1), { kind: "rate", rate: expect.closeTo(0.95, 6) }],
  ["more than 2 s too close, with recording to spare: seek back", reading(4), { kind: "seek", by: -6 }],
  ["more than 2 s too far behind: seek forward", reading(25), { kind: "seek", by: 15 }],
  ["too close, and the recording isn't long enough: pause", reading(3, 2), { kind: "hold" }],
  ["holding, delay not built up yet: keep holding", reading(8, 0, true), { kind: "none" }],
  ["holding, delay built up: play", reading(10, 0, true), { kind: "resume" }],
])("%s", (_case, playback, expected) => {
  expect(correction(playback, TARGET, NO_SEEKS, NOW)).toEqual(expected);
});

test("seeks at most once every 10 s: in between it waits", () => {
  const justSeeked: SeekHistory = { lastSeekAt: NOW - 1_000, misses: 0 };
  expect(correction(reading(25), TARGET, justSeeked, NOW)).toEqual({ kind: "wait" });
  expect(correction(reading(25), TARGET, justSeeked, NOW - 1_000 + SEEK_COOLDOWN_MS)).toEqual({ kind: "seek", by: 15 });
});

test("three seeks that didn't land: stuck, and no more seeking", () => {
  expect(correction(reading(25), TARGET, { lastSeekAt: NOW - SEEK_COOLDOWN_MS, misses: 3 }, NOW)).toEqual({ kind: "stuck" });
});

test("a seek's history: the first seek, a miss after it, and landing clears it", () => {
  const first = nextHistory(NO_SEEKS, { kind: "seek", by: 5 }, NOW);
  expect(first).toEqual({ lastSeekAt: NOW, misses: 0 });
  const missed = nextHistory(first, { kind: "seek", by: 5 }, NOW + SEEK_COOLDOWN_MS);
  expect(missed.misses).toBe(1);
  expect(nextHistory(missed, { kind: "wait" }, NOW)).toBe(missed);
  expect(nextHistory(missed, { kind: "rate", rate: 0.97 }, NOW)).toEqual(NO_SEEKS);
  expect(nextHistory(missed, { kind: "none" }, NOW)).toEqual(NO_SEEKS);
});

test.each([
  ["on the grid", 12.3, 12.3],
  ["between steps, to the nearest tenth", 12.34, 12.3],
  ["below zero, to zero", -3, 0],
  ["past five minutes, to five minutes", 400, 300],
])("delays are clamped: %s", (_case, seconds, expected) => {
  expect(clampDelay(seconds)).toBe(expected);
});

test.each([
  ["a tenth at a time", 0.1 + 0.2, 0.3],
  ["no more than 10 s early", -12, -10],
  ["no more than 10 s late", 10.4, 10],
])("fine-tune is clamped: %s", (_case, seconds, expected) => {
  expect(clampFineTune(seconds)).toBe(expected);
});

test("nudges for setting the delay by hand go both ways, big and small", () => {
  expect(DELAY_NUDGES).toEqual([-5, -1, 1, 5]);
});

test.each([
  [7, "7.0 s"],
])("seconds read with one decimal: %s", (seconds, text) => {
  expect(formatSeconds(seconds)).toBe(text);
});

test.each([
  [0.3, "+0.3 s"],
  [-1.2, "−1.2 s"],
  [0, "0.0 s"],
])("an offset reads with its sign: %s", (seconds, text) => {
  expect(formatOffset(seconds)).toBe(text);
});

test.each([
  [42, "0:42"],
  [135, "2:15"],
  [-3, "0:00"],
])("time behind reads like a clock: %s", (seconds, text) => {
  expect(formatBehind(seconds)).toBe(text);
});
