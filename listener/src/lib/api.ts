/** The commentary-sync API, as the listener app calls it: the shared client
 * (client/src/api.ts) bound to the app's API address and timeout. */

import { createApi } from "@commentary-sync/client/api";

import { API_URL, REQUEST_TIMEOUT_MS } from "@/config";

export const api = createApi({ baseUrl: API_URL, timeoutMs: REQUEST_TIMEOUT_MS });
