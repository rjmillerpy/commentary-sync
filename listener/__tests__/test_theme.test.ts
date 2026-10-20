import { COLOR, MIN_TOUCH } from "@/theme";

test("tap targets are at least 44 points, the platforms' guideline", () => {
  expect(MIN_TOUCH).toBeGreaterThanOrEqual(44);
});

test("every colour is a hex colour", () => {
  expect(Object.values(COLOR).every((colour) => /^#[0-9a-f]{6}$/.test(colour))).toBe(true);
});
