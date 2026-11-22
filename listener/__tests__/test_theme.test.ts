import { COLOR, MIN_TOUCH, PRIMARY_TOUCH, SPACE, STATUS } from "@/theme";

const AA_TEXT = 4.5; // WCAG 2.2 AA, normal text

/** WCAG's relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16) / 255);
  const [red, green, blue] = channels.map((value) => (value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
  return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!;
}

function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light! + 0.05) / (dark! + 0.05);
}

test("tap targets meet Android's 48 dp, and the main control is bigger", () => {
  expect(MIN_TOUCH).toBeGreaterThanOrEqual(48);
  expect(PRIMARY_TOUCH).toBeGreaterThanOrEqual(56);
});

test("spacing is on the 4-point grid", () => {
  expect(Object.values(SPACE).every((space) => space % 4 === 0)).toBe(true);
});

test("every colour is a hex colour", () => {
  expect([...Object.values(COLOR), ...Object.values(STATUS)].every((colour) => /^#[0-9a-f]{6}$/.test(colour))).toBe(true);
});

const TEXT_COLOURS = { text: COLOR.text, muted: COLOR.muted, accentText: COLOR.accentText, ...STATUS };

test.each(Object.entries(TEXT_COLOURS))("%s text is readable on every background (4.5:1)", (_name, colour) => {
  for (const background of [COLOR.background, COLOR.surface, COLOR.raised]) {
    expect(contrast(colour, background)).toBeGreaterThanOrEqual(AA_TEXT);
  }
});

test("the filled button's label is readable on the accent", () => {
  expect(contrast(COLOR.onAccent, COLOR.accent)).toBeGreaterThanOrEqual(AA_TEXT);
});
