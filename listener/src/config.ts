/** Settings the app is built with. EXPO_PUBLIC_* values are compiled into the
 * app, so nothing here may be a secret. */

const LOCAL_API_URL = "http://localhost:8000";

/** The commentary-sync API. On a phone, localhost is the phone: set
 * EXPO_PUBLIC_API_URL to the laptop's address on the Wi-Fi. */
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? LOCAL_API_URL;

/** Every API call gives up after this long (rule 67). */
export const REQUEST_TIMEOUT_MS = 10_000;
