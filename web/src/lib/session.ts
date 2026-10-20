/** One browser tab's sign-in. The refresh token is kept in sessionStorage,
 * so a reload mid-broadcast stays signed in; it is gone when the tab closes.
 * The access token lives only in memory. */

import { Session as ClientSession, type TokenStore } from "@commentary-sync/client/session";

import { api } from "@/lib/api";

export type { TokenStore };

export const REFRESH_TOKEN_KEY = "commentary-sync.refresh-token";

/** sessionStorage, or nothing when the browser refuses it (private modes
 * can): then a reload just signs the user out. */
export const tabStorage: TokenStore = {
  read() {
    try {
      return window.sessionStorage.getItem(REFRESH_TOKEN_KEY);
    } catch {
      return null; // storage blocked: behave as if nothing was stored
    }
  },
  write(token) {
    try {
      if (token === null) window.sessionStorage.removeItem(REFRESH_TOKEN_KEY);
      else window.sessionStorage.setItem(REFRESH_TOKEN_KEY, token);
    } catch {
      // storage blocked: the session still works until the tab reloads
    }
  },
};

/** The shared client's session (client/src/session.ts), calling the studio's API. */
export class Session extends ClientSession {
  constructor(store: TokenStore) {
    super(api, store);
  }
}
