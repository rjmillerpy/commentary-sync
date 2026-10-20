import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { SessionProvider, useSession } from "@/hooks/useSession";
import { ApiError } from "@/lib/api";
import { FakeApi, PAIR, PAIR_2 } from "../_fakeApi";
import { MemoryStore } from "../_memoryStore";

let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR_2 })
    .on("POST", "/auth/logout", { status: 204 })
    .install();
});

function withStore(store: MemoryStore) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <SessionProvider store={store}>{children}</SessionProvider>;
  };
}

test("starts signed out with nothing stored", () => {
  const { result } = renderHook(useSession, { wrapper: withStore(new MemoryStore()) });
  expect(result.current.status).toBe("signed-out");
});

test("signs in and out", async () => {
  const { result } = renderHook(useSession, { wrapper: withStore(new MemoryStore()) });
  await act(() => result.current.signIn("fan@example.com", "pw"));
  expect(result.current.status).toBe("signed-in");
  await act(() => result.current.signOut());
  expect(result.current.status).toBe("signed-out");
});

test("registering signs in", async () => {
  const { result } = renderHook(useSession, { wrapper: withStore(new MemoryStore()) });
  await act(() => result.current.register({ email: "a@example.com", password: "p", display_name: "A" }));
  expect(result.current.status).toBe("signed-in");
});

test.each([
  ["a working token", { status: 200, body: PAIR_2 }, "signed-in"],
  ["a refused token", { status: 401, body: { detail: "Invalid refresh token" } }, "signed-out"],
])("restores from %s after a reload", async (_case, reply, expected) => {
  fake.on("POST", "/auth/refresh", reply);
  const { result } = renderHook(useSession, { wrapper: withStore(new MemoryStore("refresh-1")) });
  expect(result.current.status).toBe("restoring");
  await waitFor(() => expect(result.current.status).toBe(expected));
});

test("a session the API ends signs the studio out", async () => {
  fake.on("POST", "/auth/refresh", { status: 401, body: { detail: "Invalid refresh token" } });
  const { result } = renderHook(useSession, { wrapper: withStore(new MemoryStore()) });
  await act(() => result.current.signIn("fan@example.com", "pw"));
  const expired = async () => {
    throw new ApiError(401, "expired");
  };
  await act(() => expect(result.current.authorized(expired)).rejects.toMatchObject({ status: 401 }));
  expect(result.current.status).toBe("signed-out");
});

test("authorized calls get the access token", async () => {
  const { result } = renderHook(useSession, { wrapper: withStore(new MemoryStore()) });
  await act(() => result.current.signIn("fan@example.com", "pw"));
  await expect(result.current.authorized(async (token) => token)).resolves.toBe("access-1");
});

test("unmounting mid-restore changes nothing", async () => {
  const { result, unmount } = renderHook(useSession, { wrapper: withStore(new MemoryStore("refresh-1")) });
  unmount();
  await waitFor(() => expect(fake.requests).toHaveLength(1));
  expect(result.current.status).toBe("restoring");
});

test("needs a provider", () => {
  jest.spyOn(console, "error").mockImplementation(() => undefined);
  expect(() => renderHook(useSession)).toThrow("useSession needs a SessionProvider above it");
});
