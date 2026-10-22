import { assessRoom, canGoLive, isTvLouder, percentile, type TvCheckResult, WATCH_REPORTS } from "@/lib/tvCheck";

const repeat = (level: number, count = 100) => Array<number>(count).fill(level);

test.each([
  ["a quiet room", repeat(-80), repeat(-20), "clear", -40],
  ["a TV well below the voice", repeat(-45), repeat(-20), "clear", -39],
  ["a TV a little below the voice", repeat(-35), repeat(-20), "faint", -29],
  ["a TV nearly as loud as the voice", repeat(-28), repeat(-20), "too-loud", -22],
  ["no voice at all", repeat(-80), repeat(-75), "no-voice", -74],
  ["no reports", [], [], "no-voice", -94],
])("verdict and threshold: %s", (_case, quiet, talking, verdict, thresholdDb) => {
  const result = assessRoom(quiet, talking);
  expect(result.verdict).toBe(verdict);
  expect(result.thresholdDb).toBeCloseTo(thresholdDb);
});

test("the TV's loudest moments count, and the voice's typical ones", () => {
  const quiet = [...repeat(-60, 90), ...repeat(-30, 10)]; // a crowd roar, 10% of the time
  const talking = [...repeat(-70, 20), ...repeat(-15, 80)]; // pauses between words
  const result = assessRoom(quiet, talking);
  expect(result.tvDb).toBe(-30);
  expect(result.voiceDb).toBe(-15);
  expect(result.verdict).toBe("faint");
});

test.each([
  ["clear", true],
  ["faint", true],
  ["too-loud", false],
  ["no-voice", false],
] as const)("going live after a %s check: %s", (verdict, expected) => {
  expect(canGoLive({ verdict, tvDb: 0, voiceDb: 0, thresholdDb: 0 })).toBe(expected);
});

test("going live without a check is not allowed", () => {
  expect(canGoLive(null)).toBe(false);
});

test.each([
  ["the lowest", 0, 1],
  ["the median", 0.5, 2],
  ["the highest", 1, 4],
])("percentile: %s", (_case, share, expected) => {
  expect(percentile([4, 1, 3, 2], share)).toBe(expected);
});

describe("the live watch", () => {
  const checked: TvCheckResult = { verdict: "clear", tvDb: -50, voiceDb: -20, thresholdDb: -40 };

  test.each([
    ["a TV as loud as at the check", repeat(-50, WATCH_REPORTS), false],
    ["talking over that TV", [...repeat(-50, WATCH_REPORTS / 2), ...repeat(-20, WATCH_REPORTS / 2)], false],
    ["a TV turned up", repeat(-40, WATCH_REPORTS), true],
    ["too soon to tell", repeat(-40, WATCH_REPORTS - 1), false],
  ])("%s", (_case, recent, expected) => {
    expect(isTvLouder(recent, checked)).toBe(expected);
  });
});
