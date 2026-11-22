/** Rendering with the app's guest access (hooks/useAccess.tsx), against the
 * API faked at `fetch` (the shared client's FakeApi). */

import { FakeApi, GUEST } from "@commentary-sync/client/testing";
import { render } from "@testing-library/react-native";
import type { ReactElement, ReactNode } from "react";

import { AccessProvider } from "@/hooks/useAccess";

/** The API a guest listener talks to; add routes with `.on(...)`. */
export function listenerApi(): FakeApi {
  return new FakeApi().on("POST", "/auth/guest", { status: 200, body: GUEST }).install();
}

/** A wrapper for renderHook: the hook gets the app's guest access. */
export function withAccess({ children }: { children: ReactNode }) {
  return <AccessProvider>{children}</AccessProvider>;
}

export async function renderWithAccess(ui: ReactElement) {
  return render(<AccessProvider>{ui}</AccessProvider>);
}
