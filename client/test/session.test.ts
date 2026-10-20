import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { ApiError, createApi } from "../src/api.ts";
import { Session, type TokenStore } from "../src/session.ts";
import { BASE_URL, FakeApi, PAIR, PAIR_2 } from "../src/testing.ts";

class MemoryStore implements TokenStore {
  token: string | null;
  constructor(token: string | null = null) {
    this.token = token;
  }
  read(): string | null {
    return this.token;
  }
  write(token: string | null): void {
    this.token = token;
  }
}

const api = createApi({ baseUrl: BASE_URL, timeoutMs: 1_000 });
const sessionWith = (store: TokenStore = new MemoryStore()) => new Session(api, store);
let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR_2 })
    .on("POST", "/auth/logout", { status: 204 })
    .install();
});

test("signing in keeps the refresh token for a restart", async () => {
  const store = new MemoryStore();
  const session = sessionWith(store);
  assert.equal(session.canRestore, false);
  await session.signIn("fan@example.com", "pw");
  assert.equal(store.token, "refresh-1");
  assert.equal(session.canRestore, true);
});

test("registering signs in too", async () => {
  const store = new MemoryStore();
  await sessionWith(store).register({ email: "a@example.com", password: "p", display_name: "A" });
  assert.equal(store.token, "refresh-1");
});

test("calls carry the access token", async () => {
  const session = sessionWith();
  await session.signIn("fan@example.com", "pw");
  assert.equal(await session.authorized(async (token) => token), "access-1");
});

test("after a restart, the stored refresh token signs back in", async () => {
  const store = new MemoryStore("refresh-1");
  const session = sessionWith(store);
  assert.equal(await session.restore(), true);
  assert.equal(store.token, "refresh-2"); // rotated
  assert.equal(await session.authorized(async (token) => token), "access-2");
});

test("restoring with nothing stored is just signed out", async () => {
  assert.equal(await sessionWith().restore(), false);
  assert.deepEqual(fake.requests, []);
});

test("a refresh token the API refuses signs out", async () => {
  fake.on("POST", "/auth/refresh", { status: 401, body: { detail: "Invalid refresh token" } });
  const store = new MemoryStore("stale");
  const session = sessionWith(store);
  assert.equal(await session.restore(), false);
  assert.equal(store.token, null);
  assert.equal(session.canRestore, false);
});

test("an expired access token is renewed once and the call retried", async () => {
  const session = sessionWith();
  await session.signIn("fan@example.com", "pw");
  const seen: string[] = [];
  const result = await session.authorized(async (token) => {
    seen.push(token);
    if (token === "access-1") throw new ApiError(401, "expired");
    return "done";
  });
  assert.equal(result, "done");
  assert.deepEqual(seen, ["access-1", "access-2"]);
});

test("other failures are not retried", async () => {
  const session = sessionWith();
  await session.signIn("fan@example.com", "pw");
  let calls = 0;
  const conflict = async () => {
    calls += 1;
    throw new ApiError(409, "conflict");
  };
  await assert.rejects(session.authorized(conflict), { status: 409 });
  assert.equal(calls, 1);
});

test("regression: calls that expire together share one refresh", async () => {
  // Refresh tokens rotate; sending the same one twice looks like theft and
  // the API revokes the whole session.
  const session = sessionWith(new MemoryStore("refresh-1"));
  await Promise.all([session.authorized(async () => 1), session.authorized(async () => 2)]);
  assert.equal(fake.paths().filter((path) => path === "POST /auth/refresh").length, 1);
});

test("without any token, a call says the session has ended", async () => {
  await assert.rejects(sessionWith().authorized(async () => 1), {
    status: 401,
    detail: "Your session has ended. Sign in again.",
  });
});

test("offline during a refresh keeps the token to try again", async () => {
  const store = new MemoryStore("refresh-1");
  fake.offline = true;
  await assert.rejects(sessionWith(store).authorized(async () => 1), { status: 0 });
  assert.equal(store.token, "refresh-1");
});

test("signing out forgets the tokens and ends the API session", async () => {
  const store = new MemoryStore();
  const session = sessionWith(store);
  await session.signIn("fan@example.com", "pw");
  await session.signOut();
  assert.equal(store.token, null);
  assert.deepEqual(fake.requests.at(-1)?.body, { refresh_token: "refresh-1" });
  assert.equal(fake.requests.at(-1)?.path, "/auth/logout");
});

test("signing out offline still signs out here", async () => {
  const store = new MemoryStore();
  const session = sessionWith(store);
  await session.signIn("fan@example.com", "pw");
  fake.offline = true;
  await session.signOut();
  assert.equal(store.token, null);
});

test("signing out when never signed in calls nothing", async () => {
  await sessionWith().signOut();
  assert.deepEqual(fake.requests, []);
});
