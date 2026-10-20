import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { BASE_URL, FakeApi } from "../src/testing.ts";

let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi().install();
});

test("an unknown route is a 404, and is recorded", async () => {
  const response = await fetch(`${BASE_URL}/nowhere?x=1`);
  assert.equal(response.status, 404);
  assert.deepEqual(fake.paths(), ["GET /nowhere?x=1"]);
});

test("replies are used in order, and the last one repeats", async () => {
  fake.on("POST", "/streams/s-1/listener-playlist", { status: 409, body: { detail: "No HLS audio yet" } }, { status: 200, body: { url: "u" } });
  const statuses = [];
  for (let attempt = 0; attempt < 3; attempt += 1) {
    statuses.push((await fetch(`${BASE_URL}/streams/s-1/listener-playlist`, { method: "POST" })).status);
  }
  assert.deepEqual(statuses, [409, 200, 200]);
});

test("a reply without a body has no JSON", async () => {
  fake.on("POST", "/auth/logout", { status: 204 });
  const response = await fetch(`${BASE_URL}/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: "r" }),
  });
  assert.equal(response.status, 204);
  assert.deepEqual(fake.requests[0]?.body, { refresh_token: "r" });
  assert.equal(fake.requests[0]?.authorization, null);
});

test("a route given no replies answers 404", async () => {
  fake.on("GET", "/events");
  assert.equal((await fetch(`${BASE_URL}/events`)).status, 404);
});

test("a body that isn't JSON is recorded as it was sent", async () => {
  fake.on("POST", "/streams/s-1/reference", { status: 204 });
  const pcm = new Uint8Array([1, 2]);
  await fetch(`${BASE_URL}/streams/s-1/reference`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: pcm });
  assert.equal(fake.requests[0]?.body, pcm);
  assert.equal(fake.requests[0]?.contentType, "application/octet-stream");
});

test("a route without a query answers any query; an exact one wins", async () => {
  fake.on("POST", "/streams/s-1/sync", { status: 200, body: { any: true } });
  fake.on("POST", "/streams/s-1/sync?captured_at=1", { status: 200, body: { exact: true } });
  const any = await (await fetch(`${BASE_URL}/streams/s-1/sync?captured_at=2`, { method: "POST" })).json();
  const exact = await (await fetch(`${BASE_URL}/streams/s-1/sync?captured_at=1`, { method: "POST" })).json();
  assert.deepEqual([any, exact], [{ any: true }, { exact: true }]);
});
