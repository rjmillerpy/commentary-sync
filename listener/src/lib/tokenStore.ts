/** Where the refresh token survives the app closing: the phone's secure
 * storage (Keychain on iOS, Keystore-backed on Android), never plain files. */

import type { TokenStore } from "@commentary-sync/client/session";
import * as SecureStore from "expo-secure-store";

export const REFRESH_TOKEN_KEY = "commentary-sync.refresh-token";

export const secureStorage: TokenStore = {
  read() {
    try {
      return SecureStore.getItem(REFRESH_TOKEN_KEY);
    } catch {
      return null; // storage unavailable: start signed out
    }
  },
  write(token) {
    try {
      if (token === null) void SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY).catch(() => undefined);
      else SecureStore.setItem(REFRESH_TOKEN_KEY, token);
    } catch {
      // storage unavailable: signed in until the app closes
    }
  },
};
