"use client";

/** The signed-in state for the whole studio: the shared SessionProvider
 * (client/src/react.ts) with one Session per tab, kept in sessionStorage. */

import { SessionProvider as SharedSessionProvider } from "@commentary-sync/client/react";
import { type ReactNode, useCallback } from "react";

import { Session, type TokenStore, tabStorage } from "@/lib/session";

export { type SessionStatus, type SessionValue, useSession } from "@commentary-sync/client/react";

export function SessionProvider({ children, store = tabStorage }: { children: ReactNode; store?: TokenStore }) {
  const createSession = useCallback(() => new Session(store), [store]);
  return <SharedSessionProvider createSession={createSession}>{children}</SharedSessionProvider>;
}
