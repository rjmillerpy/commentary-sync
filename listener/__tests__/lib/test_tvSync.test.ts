import { LIVE_FLOOR_SECONDS, planDelay } from "@/lib/tvSync";

test.each([
  ["far behind: delay to match, no pause", 23.4, { delay: 23.5, pauseTv: 0 }],
  ["just at the floor", LIVE_FLOOR_SECONDS, { delay: LIVE_FLOOR_SECONDS, pauseTv: 0 }],
  ["behind, but less than the commentary can be: pause the rest", 1.2, { delay: LIVE_FLOOR_SECONDS, pauseTv: 3 }],
  ["level with the commentator", 0, { delay: LIVE_FLOOR_SECONDS, pauseTv: 4 }],
  ["ahead of the commentator: pause for the lead and the floor", -6.3, { delay: LIVE_FLOOR_SECONDS, pauseTv: 10.5 }],
])("%s", (_case, behind, expected) => {
  expect(planDelay(behind)).toEqual(expected);
});
