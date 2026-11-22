/** Style tokens: every size and colour the app uses, in one place
 * (UI rule 11: a 4/8 grid, at most five type sizes, one accent colour,
 * and green, amber and red only ever for sync and system state). */

export const SPACE = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const FONT = { small: 14, body: 16, large: 20, title: 24, big: 32 } as const;
export const RADIUS = 12;
export const MIN_TOUCH = 48; // Android's 48 dp, above iOS's 44 pt
export const PRIMARY_TOUCH = 56; // the main control on a screen
export const DIMMED = 0.5; // the opacity of something busy or unavailable

export const COLOR = {
  background: "#0f1115",
  surface: "#1a1d24",
  raised: "#262a33",
  text: "#f2f3f5",
  muted: "#a3a9b4",
  /** The one accent: the filled button and links. */
  accent: "#2f6fe4",
  accentText: "#8ab4ff",
  onAccent: "#ffffff",
} as const;

/** Sync and system state only: never decoration. Each is paired with an
 * icon and words wherever it's used, so colour is never the only signal. */
export const STATUS = {
  good: "#4ac26b",
  working: "#6cb6ff",
  warning: "#e3b341",
  error: "#ff7b72",
  neutral: "#c9d1d9",
  off: "#9ba3ae",
  live: "#ff7b72",
} as const;
