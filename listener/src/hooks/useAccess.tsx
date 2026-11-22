/** Listening needs no account (UI rule 7.2): every call that wants a
 * token gets a guest's (@commentary-sync/client/guest). One GuestPass for
 * the whole app, from AccessProvider; `useAuthorized` hands out its
 * `authorized`, the same shape a signed-in Session has. */

import { GuestPass } from "@commentary-sync/client/guest";
import { createContext, type ReactNode, useContext, useMemo, useState } from "react";

import { api } from "@/lib/api";

export type Authorized = <T>(action: (accessToken: string) => Promise<T>) => Promise<T>;

const AccessContext = createContext<Authorized | null>(null);

const createPass = () => new GuestPass(api);

export function AccessProvider({ children }: { children: ReactNode }) {
  const [pass] = useState(createPass);
  const authorized = useMemo<Authorized>(() => (action) => pass.authorized(action), [pass]);
  return <AccessContext.Provider value={authorized}>{children}</AccessContext.Provider>;
}

export function useAuthorized(): Authorized {
  const authorized = useContext(AccessContext);
  if (authorized === null) throw new Error("useAuthorized needs an AccessProvider above it");
  return authorized;
}
