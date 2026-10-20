/** The signed-in state for a whole React app, from one Session: the studio
 * and the listener app both wrap themselves in a SessionProvider.
 *
 * Plain createElement, not JSX, so Node can run this file by stripping its
 * types (client/test runs on `node --test`).
 */

import {
  createContext,
  createElement,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { Registration } from "./api.ts";
import type { Session } from "./session.ts";

export type SessionStatus = "restoring" | "signed-out" | "signed-in";

export interface SessionValue {
  status: SessionStatus;
  signIn(email: string, password: string): Promise<void>;
  register(registration: Registration): Promise<void>;
  signOut(): Promise<void>;
  authorized<T>(action: (accessToken: string) => Promise<T>): Promise<T>;
}

export interface SessionProviderProps {
  /** Called once, on first render: the app's Session with its own API and token store. */
  createSession: () => Session;
  children?: ReactNode;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ createSession, children }: SessionProviderProps) {
  const [session] = useState(createSession);
  const [status, setStatus] = useState<SessionStatus>(() => (session.canRestore ? "restoring" : "signed-out"));

  useEffect(() => {
    if (status !== "restoring") return;
    let isCurrent = true;
    void session.restore().then((restored) => {
      if (isCurrent) setStatus(restored ? "signed-in" : "signed-out");
    });
    return () => {
      isCurrent = false;
    };
  }, [session, status]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      await session.signIn(email, password);
      setStatus("signed-in");
    },
    [session],
  );
  const register = useCallback(
    async (registration: Registration) => {
      await session.register(registration);
      setStatus("signed-in");
    },
    [session],
  );
  const signOut = useCallback(async () => {
    await session.signOut();
    setStatus("signed-out");
  }, [session]);
  const authorized = useCallback(
    async <T>(action: (accessToken: string) => Promise<T>): Promise<T> => {
      try {
        return await session.authorized(action);
      } finally {
        if (!session.canRestore) setStatus("signed-out"); // the API ended the session
      }
    },
    [session],
  );

  const value = useMemo(
    () => ({ status, signIn, register, signOut, authorized }),
    [status, signIn, register, signOut, authorized],
  );
  return createElement(SessionContext.Provider, { value }, children);
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession needs a SessionProvider above it");
  return value;
}
