/** The listener's signed-in account: the shared Session, calling the app's
 * API and keeping the refresh token in secure storage. */

import { Session as ClientSession, type TokenStore } from "@commentary-sync/client/session";

import { api } from "@/lib/api";
import { secureStorage } from "@/lib/tokenStore";

export class Session extends ClientSession {
  constructor(store: TokenStore = secureStorage) {
    super(api, store);
  }
}
