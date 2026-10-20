import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { ApiError, createApi } from "../src/api.ts";
import {
  BASE_URL,
  COMMENTATOR,
  EVENTS,
  FakeApi,
  PAIR,
  PLAYLIST,
  ROOM,
  STREAM,
  STREAMS,
  SYNC_MATCHED,
  SYNC_NOT_FOUND,
} from "../src/testing.ts";

const TIMEOUT_MS = 1_000;
const SIGNED_IN = "Bearer tok";
let fake: FakeApi;
const api = createApi({ baseUrl: `${BASE_URL}/`, timeoutMs: TIMEOUT_MS });

beforeEach(() => {
  fake = new FakeApi().install();
});

test("logging in posts the credentials and returns the pair", async () => {
  fake.on("POST", "/auth/login", { status: 200, body: PAIR });
  const pair = await api.login("fan@example.com", "correct horse battery");
  assert.equal(pair.access_token, "access-1");
  assert.deepEqual(fake.requests[0]?.body, { email: "fan@example.com", password: "correct horse battery" });
  assert.equal(fake.requests[0]?.authorization, null);
});

test("every endpoint calls its path, with the access token where it needs one", async () => {
  fake
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR })
    .on("POST", "/auth/logout", { status: 204 })
    .on("GET", "/commentators/me", { status: 200, body: COMMENTATOR })
    .on("POST", "/commentators", { status: 201, body: COMMENTATOR })
    .on("GET", "/events?limit=100", { status: 200, body: EVENTS })
    .on("GET", "/streams?event_id=e-live&limit=100", { status: 200, body: STREAMS })
    .on("POST", "/streams", { status: 201, body: STREAM })
    .on("POST", "/streams/s-1/publisher-token", { status: 200, body: ROOM })
    .on("POST", "/streams/s-1/listener-playlist", { status: 200, body: PLAYLIST })
    .on("POST", "/streams/s-1/end", { status: 200, body: STREAM });
  await api.register({ email: "a@example.com", password: "p", display_name: "A" });
  await api.refresh("refresh-1");
  assert.equal(await api.logout("refresh-1"), null);
  await api.myCommentatorProfile("tok");
  await api.becomeCommentator("tok", "fan_cast");
  await api.upcomingEvents();
  assert.equal((await api.liveStreamsOn("e-live")).items[0]?.commentator.handle, "fan_cast");
  await api.goLive("tok", "e-live");
  await api.publisherToken("tok", "s-1");
  assert.deepEqual(await api.listenerPlaylist("tok", "s-1"), PLAYLIST);
  await api.endStream("tok", "s-1");
  assert.deepEqual(
    fake.requests.map((request) => [`${request.method} ${request.path}`, request.authorization]),
    [
      ["POST /auth/register", null],
      ["POST /auth/refresh", null],
      ["POST /auth/logout", null],
      ["GET /commentators/me", SIGNED_IN],
      ["POST /commentators", SIGNED_IN],
      ["GET /events?limit=100", null],
      ["GET /streams?event_id=e-live&limit=100", null],
      ["POST /streams", SIGNED_IN],
      ["POST /streams/s-1/publisher-token", SIGNED_IN],
      ["POST /streams/s-1/listener-playlist", SIGNED_IN],
      ["POST /streams/s-1/end", SIGNED_IN],
    ],
  );
  assert.deepEqual(fake.requests[7]?.body, { event_id: "e-live" });
});

test("security: a stream ID can't change the path it is put in", async () => {
  await api.endStream("tok", "../auth/logout").catch(() => undefined);
  assert.equal(fake.requests[0]?.path, "/streams/..%2Fauth%2Flogout/end");
});

test("security: a handle or event ID can't add query parameters", async () => {
  await api.liveStreamOf("x&limit=100").catch(() => undefined);
  await api.liveStreamsOn("e&commentator=y").catch(() => undefined);
  assert.deepEqual(fake.paths(), [
    "GET /streams?commentator=x%26limit%3D100&limit=1",
    "GET /streams?event_id=e%26commentator%3Dy&limit=100",
  ]);
});

test("each call is given a timeout", async () => {
  fake.on("GET", "/events?limit=100", { status: 200, body: EVENTS });
  await api.upcomingEvents();
  assert.ok(fake.requests[0]?.signal instanceof AbortSignal);
});

for (const [name, reply, status, detail] of [
  ["a sentence", { status: 409, body: { detail: "Handle already taken" } }, 409, "Handle already taken"],
  [
    "validation issues",
    { status: 422, body: { detail: [{ type: "x", loc: ["body", "handle"], msg: "Too short" }, { msg: "Bad pattern" }] } },
    422,
    "Too short; Bad pattern",
  ],
  ["a body that isn't JSON", { status: 502 }, 502, "Something went wrong; try again."],
  ["an unexpected body", { status: 500, body: { error: "boom" } }, 500, "Something went wrong; try again."],
] as const) {
  test(`an error with ${name} becomes an ApiError`, async () => {
    fake.on("POST", "/commentators", reply);
    await assert.rejects(api.becomeCommentator("tok", "x"), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.deepEqual([error.name, error.status, error.detail], ["ApiError", status, detail]);
      return true;
    });
  });
}

test("no answer at all is status 0 with a plain sentence", async () => {
  fake.offline = true;
  await assert.rejects(api.upcomingEvents(), {
    status: 0,
    detail: "Can't reach the server. Check your connection and try again.",
  });
});

test("a response of the wrong shape is refused, not passed on", async () => {
  fake.on("GET", "/commentators/me", { status: 200, body: { handle: 7 } });
  await assert.rejects(api.myCommentatorProfile("tok"));
});

for (const [name, body, expected] of [
  ["a live stream", { items: [STREAM], next_offset: null }, "s-1"],
  ["none", { items: [], next_offset: null }, null],
] as const) {
  test(`finding a commentator's live stream: ${name}`, async () => {
    fake.on("GET", "/streams?commentator=fan_cast&limit=1", { status: 200, body });
    assert.equal((await api.liveStreamOf("fan_cast"))?.id ?? null, expected);
  });
}

test("the server's time is read from the clock", async () => {
  fake.on("GET", "/clock", { status: 200, body: { now: 1_792_342_800.25 } });
  assert.equal(await api.serverTime(), 1_792_342_800.25);
});

test("reference audio goes as raw bytes with its capture time", async () => {
  fake.on("POST", "/streams/s-1/reference?captured_at=1792342800.5", { status: 204 });
  const pcm = new Uint8Array([0, 1, 2, 3]);
  assert.equal(await api.sendReference("tok", "s-1", pcm, 1_792_342_800.5), null);
  assert.deepEqual(
    [fake.requests[0]?.body, fake.requests[0]?.contentType, fake.requests[0]?.authorization],
    [pcm, "application/octet-stream", SIGNED_IN],
  );
});

for (const [name, reply, expected] of [
  ["a match gives the delay", SYNC_MATCHED, { status: "matched", delay_seconds: 23.5, peak_ratio: 3.2 }],
  ["no match says so", SYNC_NOT_FOUND, { status: "not_found" }],
] as const) {
  test(`syncing to the TV: ${name}`, async () => {
    fake.on("POST", "/streams/s-1/sync?captured_at=1792342800", { status: 200, body: reply });
    const features = { frames: 1, values: new Float32Array(16) };
    assert.deepEqual(await api.syncToTv("tok", "s-1", features, 1_792_342_800), expected);
    assert.equal(fake.requests[0]?.body, features.values);
  });
}

test("one stream is public, by ID", async () => {
  fake.on("GET", "/streams/s-1", { status: 200, body: STREAM });
  assert.equal((await api.getStream("s-1")).status, "live");
  assert.equal(fake.requests[0]?.authorization, null);
});

test("checking in as a listener is a signed-in POST with no body", async () => {
  fake.on("POST", "/streams/s-1/listening", { status: 204 });
  assert.equal(await api.listening("tok", "s-1"), null);
  assert.deepEqual([fake.requests[0]?.authorization, fake.requests[0]?.body], [SIGNED_IN, null]);
});
