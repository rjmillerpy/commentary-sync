import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { ApiError, createApi } from "../src/api.ts";
import { GuestPass } from "../src/guest.ts";
import { BASE_URL, FakeApi, GUEST } from "../src/testing.ts";

const api = createApi({ baseUrl: BASE_URL, timeoutMs: 1_000 });
let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi().on("POST", "/auth/guest", { status: 200, body: GUEST }).install();
});

test("a guest token is fetched once, on first use, and reused", async () => {
  const pass = new GuestPass(api);
  assert.deepEqual(fake.paths(), []);
  const tokens = await Promise.all([1, 2, 3].map(() => pass.authorized(async (token) => token)));
  assert.deepEqual(tokens, ["guest-1", "guest-1", "guest-1"]);
  assert.deepEqual(fake.paths(), ["POST /auth/guest"]); // one request, though three asked at once
});

test("an expired guest token is replaced once, and the action tried again", async () => {
  const pass = new GuestPass(api);
  await pass.authorized(async () => "warm");
  const seen: string[] = [];
  const result = await pass.authorized(async (token) => {
    seen.push(token);
    if (seen.length === 1) throw new ApiError(401, "Not signed in");
    return "done";
  });
  assert.equal(result, "done");
  assert.equal(fake.paths().filter((path) => path === "POST /auth/guest").length, 2);
});

test("other failures are the caller's, and keep the token", async () => {
  const pass = new GuestPass(api);
  await assert.rejects(
    pass.authorized(async () => {
      throw new ApiError(409, "This stream has already ended");
    }),
    { status: 409 },
  );
  await pass.authorized(async () => "again");
  assert.deepEqual(fake.paths(), ["POST /auth/guest"]);
});

test("no guest token (offline, or rate limited) is a failure the next call retries", async () => {
  fake.on("POST", "/auth/guest", { status: 429, body: { detail: "Too many requests" } });
  const pass = new GuestPass(api);
  await assert.rejects(pass.authorized(async () => "never"), { status: 429 });
  fake.on("POST", "/auth/guest", { status: 200, body: GUEST });
  assert.equal(await pass.authorized(async (token) => token), "guest-1");
});
