/** The studio's colours, read from the stylesheet itself: text must be
 * readable on its backgrounds (UI rule 10, WCAG AA 4.5:1) in both themes. */

import { readFileSync } from "fs";
import { join } from "path";

const CSS = readFileSync(join(__dirname, "../../src/app/globals.css"), "utf8");
const AA_TEXT = 4.5;

function tokens(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})/g)].map((match) => [match[1]!, match[2]!]));
}

const light = tokens(CSS.slice(0, CSS.indexOf("@media")));
const dark = { ...light, ...tokens(CSS.slice(CSS.indexOf("@media"))) };

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16) / 255);
  const [red, green, blue] = channels.map((value) => (value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
  return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!;
}

function contrast(foreground: string, background: string): number {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (lighter! + 0.05) / (darker! + 0.05);
}

const PAIRS: [string, string][] = [
  ["text", "bg"],
  ["text", "card"],
  ["text", "chosen"],
  ["muted", "card"],
  ["muted", "bg"],
  ["live", "card"],
  ["focus", "card"],
  ["on-accent", "accent"],
];

test.each([
  ["light", light],
  ["dark", dark],
])("every text colour is readable in the %s theme", (_theme, colours) => {
  for (const [foreground, background] of PAIRS) {
    expect({ pair: `${foreground} on ${background}`, ratio: contrast(colours[foreground]!, colours[background]!) >= AA_TEXT }).toEqual({
      pair: `${foreground} on ${background}`,
      ratio: true,
    });
  }
});

test("the danger button's white label is readable in both themes", () => {
  expect(contrast("#ffffff", light.danger!)).toBeGreaterThanOrEqual(AA_TEXT);
  expect(contrast("#ffffff", dark.danger!)).toBeGreaterThanOrEqual(AA_TEXT);
});
