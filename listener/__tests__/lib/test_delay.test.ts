import { clampDelay, correction, DELAY_NUDGES, formatSeconds } from "@/lib/delay";

const TARGET = 10;

test.each([
  ["the player doesn't know its offset yet", { offset: null, position: 30, isHolding: false }, { kind: "none" }],
  ["on target", { offset: 10, position: 30, isHolding: false }, { kind: "none" }],
  ["within the tolerance", { offset: 10.4, position: 30, isHolding: false }, { kind: "none" }],
  ["too close to live, with recording to spare: seek back", { offset: 4, position: 30, isHolding: false }, { kind: "seek", by: -6 }],
  ["too far behind: seek forward", { offset: 25, position: 30, isHolding: false }, { kind: "seek", by: 15 }],
  ["too close, and the recording isn't long enough: pause", { offset: 3, position: 2, isHolding: false }, { kind: "hold" }],
  ["holding, delay not built up yet: keep holding", { offset: 8, position: 0, isHolding: true }, { kind: "none" }],
  ["holding, delay built up: play", { offset: 10, position: 0, isHolding: true }, { kind: "resume" }],
])("%s", (_case, reading, expected) => {
  expect(correction(reading, TARGET)).toEqual(expected);
});

test.each([
  ["on the grid", 12.5, 12.5],
  ["between steps, to the nearest half second", 12.3, 12.5],
  ["below zero, to zero", -3, 0],
  ["past five minutes, to five minutes", 400, 300],
])("delays are clamped: %s", (_case, seconds, expected) => {
  expect(clampDelay(seconds)).toBe(expected);
});

test("nudges go both ways, big and small", () => {
  expect(DELAY_NUDGES).toEqual([-5, -0.5, 0.5, 5]);
});

test("seconds read with one decimal", () => {
  expect(formatSeconds(7)).toBe("7.0 s");
});
