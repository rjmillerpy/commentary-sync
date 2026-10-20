/** Rendering with a real signed-in session, against the API faked at `fetch`
 * (the shared client's FakeApi). */

import { SessionProvider } from "@commentary-sync/client/react";
import { FakeApi, PAIR, PAIR_2 } from "@commentary-sync/client/testing";
import { render } from "@testing-library/react-native";
import type { ReactElement } from "react";

import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { Session } from "@/lib/session";
import { items } from "./_fakeSecureStore";

/** The API a signed-in listener talks to; add routes with `.on(...)`. */
export function listenerApi(): FakeApi {
  return new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR_2 })
    .on("POST", "/auth/logout", { status: 204 })
    .install();
}

/** Renders `ui` inside a session restored from a stored refresh token. */
export async function renderSignedIn(ui: ReactElement) {
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
  return render(<SessionProvider createSession={() => new Session()}>{ui}</SessionProvider>);
}
