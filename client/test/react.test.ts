import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { act, createElement } from "react";
import { createRoot } from "test-renderer";

import { ApiError, createApi } from "../src/api.ts";
import { SessionProvider, type SessionValue, useSession } from "../src/react.ts";
import { Session, type TokenStore } from "../src/session.ts";
import { BASE_URL, FakeApi, PAIR, PAIR_2 } from "../src/testing.ts";

// React only flushes updates inside act() when it knows it's in a test.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const api = createApi({ baseUrl: BASE_URL, timeoutMs: 1_000 });
let fake: FakeApi;

function storeWith(token: string | null): TokenStore {
  let stored = token;
  return { read: () => stored, write: (next) => void (stored = next) };
}

/** Renders a SessionProvider and returns a getter for the latest session value. */
async function renderSession(store: TokenStore): Promise<() => SessionValue> {
  let latest: SessionValue | null = null;
  function Probe() {
    latest = useSession();
    return null;
  }
  const root = createRoot();
  await act(async () => {
    root.render(createElement(SessionProvider, { createSession: () => new Session(api, store) }, createElement(Probe)));
  });
  return () => {
    assert.ok(latest !== null);
    return latest;
  };
}

beforeEach(() => {
  fake = new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR_2 })
    .on("POST", "/auth/logout", { status: 204 })
    .install();
});

test("with nothing stored, the app starts signed out", async () => {
  const session = await renderSession(storeWith(null));
  assert.equal(session().status, "signed-out");
});

test("a stored refresh token is restored to signed in", async () => {
  const session = await renderSession(storeWith("refresh-1"));
  assert.equal(session().status, "signed-in");
});

test("a stored token the API refuses ends signed out", async () => {
  fake.on("POST", "/auth/refresh", { status: 401, body: { detail: "Invalid refresh token" } });
  const session = await renderSession(storeWith("stale"));
  assert.equal(session().status, "signed-out");
});

test("signing in, registering and signing out move the status", async () => {
  const session = await renderSession(storeWith(null));
  await act(() => session().signIn("fan@example.com", "pw"));
  assert.equal(session().status, "signed-in");
  await act(() => session().signOut());
  assert.equal(session().status, "signed-out");
  await act(() => session().register({ email: "a@example.com", password: "p", display_name: "A" }));
  assert.equal(session().status, "signed-in");
});

test("a call made after the API ends the session signs the app out", async () => {
  const session = await renderSession(storeWith(null));
  await act(() => session().signIn("fan@example.com", "pw"));
  fake.on("POST", "/auth/refresh", { status: 401, body: { detail: "Invalid refresh token" } });
  const expired = async () => {
    throw new ApiError(401, "expired");
  };
  await act(async () => {
    await assert.rejects(() => session().authorized(expired), { status: 401 });
  });
  assert.equal(session().status, "signed-out");
});

test("calls carry the access token", async () => {
  const session = await renderSession(storeWith(null));
  await act(() => session().signIn("fan@example.com", "pw"));
  let token = "";
  await act(async () => {
    token = await session().authorized(async (accessToken) => accessToken);
  });
  assert.equal(token, "access-1");
});

test("useSession outside a provider says what's missing", async () => {
  function Orphan() {
    useSession();
    return null;
  }
  // The handler replaces React's default console report of the error.
  const root = createRoot({ onUncaughtError: () => undefined });
  // act() returns a thenable, not a Promise, so it is awaited inside a function.
  await assert.rejects(async () => {
    await act(async () => {
      root.render(createElement(Orphan));
    });
  }, /useSession needs a SessionProvider above it/);
});
