import assert from "node:assert/strict";
import { test } from "node:test";

import {
  EventPageSchema,
  HANDLE_PATTERN,
  PlaylistAccessSchema,
  RoomAccessSchema,
  StreamPageSchema,
  StreamSchema,
  TokenPairSchema,
} from "../src/schema.ts";
import { EVENTS, PAIR, PLAYLIST, ROOM, STREAM, STREAMS } from "../src/testing.ts";

test("API responses parse, keeping only what the clients read", () => {
  assert.deepEqual(TokenPairSchema.parse(PAIR), { access_token: "access-1", refresh_token: "refresh-1", expires_in: 900 });
  assert.equal(EventPageSchema.parse(EVENTS).items.length, 1);
  assert.deepEqual(StreamSchema.parse(STREAM), {
    id: "s-1",
    event_id: "e-live",
    commentator: { handle: "fan_cast", display_name: "Fan" },
    status: "live",
    started_at: STREAM.started_at,
    listeners: 3,
  });
  assert.equal(StreamPageSchema.parse(STREAMS).next_offset, null);
  assert.deepEqual(RoomAccessSchema.parse(ROOM), ROOM);
  assert.deepEqual(PlaylistAccessSchema.parse(PLAYLIST), PLAYLIST);
});

for (const [name, schema, value] of [
  ["a pair without a refresh token", TokenPairSchema, { access_token: "a", expires_in: 1 }],
  ["an unknown event status", EventPageSchema, { items: [{ ...EVENTS.items[0], status: "halftime" }], next_offset: null }],
  ["an unknown stream status", StreamSchema, { ...STREAM, status: "paused" }],
  ["a stream without its commentator", StreamSchema, { ...STREAM, commentator: undefined }],
  ["a stream with a fractional listener", StreamSchema, { ...STREAM, listeners: 1.5 }],
  ["a playlist without a URL", PlaylistAccessSchema, {}],
] as const) {
  test(`rejects ${name}`, () => {
    assert.equal(schema.safeParse(value).success, false);
  });
}

for (const [name, handle, allowed] of [
  ["letters, digits and underscores", "Fan_Cast_1", true],
  ["a space", "fan cast", false],
  ["a hyphen", "fan-cast", false],
] as const) {
  test(`the handle pattern allows ${name}: ${allowed}`, () => {
    assert.equal(new RegExp(`^${HANDLE_PATTERN}$`).test(handle), allowed);
  });
}

test("a stream whose listeners can't be counted still parses", () => {
  assert.equal(StreamSchema.parse({ ...STREAM, listeners: null }).listeners, null);
});
