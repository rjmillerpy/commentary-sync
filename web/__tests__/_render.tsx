/** Rendering inside a SessionProvider, signed in or not. */

import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";

import { SessionProvider } from "@/hooks/useSession";
import { MemoryStore } from "./_memoryStore";

/** With a stored refresh token, the provider signs in on mount (POST /auth/refresh). */
export function renderSignedIn(ui: ReactElement): RenderResult {
  return render(<SessionProvider store={new MemoryStore("refresh-1")}>{ui}</SessionProvider>);
}

export function renderSignedOut(ui: ReactElement, store = new MemoryStore()): RenderResult {
  return render(<SessionProvider store={store}>{ui}</SessionProvider>);
}
