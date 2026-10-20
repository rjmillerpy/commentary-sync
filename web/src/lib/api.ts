/** The commentary-sync API, as the studio calls it: the shared client
 * (client/src/api.ts) bound to the studio's API address and timeout. */

import { createApi } from "@commentary-sync/client/api";

import { API_URL, REQUEST_TIMEOUT_MS } from "@/lib/config";

export { ApiError, HTTP_NOT_FOUND, HTTP_UNAUTHORIZED, type Registration } from "@commentary-sync/client/api";

export const api = createApi({ baseUrl: API_URL, timeoutMs: REQUEST_TIMEOUT_MS });

export const {
  register,
  login,
  refresh,
  logout,
  myCommentatorProfile,
  becomeCommentator,
  upcomingEvents,
  goLive,
  liveStreamOf,
  getStream,
  endStream,
  publisherToken,
} = api;
