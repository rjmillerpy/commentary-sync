import { backoffMs, judgeRecheck } from "@/lib/autoSync";

test.each([
  ["the same delay: keep", { delay: 20, pauseTv: 0 }, 20, "keep"],
  ["within half a second: keep", { delay: 20.5, pauseTv: 0 }, 20, "keep"],
  ["the TV fell further behind: adjust", { delay: 26, pauseTv: 0 }, 20, "adjust"],
  ["the TV caught up a little: adjust", { delay: 17, pauseTv: 0 }, 20, "adjust"],
  ["the TV is now ahead: adjust, the listener must pause it", { delay: 4, pauseTv: 3 }, 4, "adjust"],
])("%s", (_case, plan, current, expected) => {
  expect(judgeRecheck(plan, current).kind).toBe(expected);
});

test("reconnect waits grow, 1 s doubling, to at most 30 s", () => {
  expect([0, 1, 2, 3, 4, 5, 6, 10].map(backoffMs)).toEqual([1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 30_000]);
});
