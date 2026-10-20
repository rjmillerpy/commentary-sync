/** Settings the studio is built with. NEXT_PUBLIC_* values are baked into
 * the browser bundle at build time, so nothing here may be a secret. */

const LOCAL_API_URL = "http://localhost:8000";

/** The commentary-sync API, without a trailing slash. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? LOCAL_API_URL).replace(/\/+$/, "");

/** The LiveKit server the API hands out room tokens for
 * (COMMENTARY_LIVEKIT_URL): the page's Content-Security-Policy allows
 * connecting to it and nowhere else. */
export const LIVEKIT_URL = process.env.NEXT_PUBLIC_LIVEKIT_URL ?? "ws://localhost:7880";

/** Every API call gives up after this long (rule 67). */
export const REQUEST_TIMEOUT_MS = 10_000;
