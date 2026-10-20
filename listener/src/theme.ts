/** Style tokens: every size and colour the app uses, in one place. */

export const SPACE = { xs: 4, sm: 8, md: 16, lg: 24 } as const;
export const FONT = { small: 13, body: 16, title: 22, big: 34 } as const;
export const RADIUS = 10;
export const MIN_TOUCH = 44; // the smallest comfortable tap target, in points
export const DIMMED = 0.5; // the opacity of something busy or unavailable

export const COLOR = {
  background: "#0f1115",
  surface: "#1a1d24",
  text: "#f2f3f5",
  muted: "#9aa0ab",
  accent: "#4f8cff",
  live: "#ff4d4f",
  danger: "#ff7875",
} as const;
