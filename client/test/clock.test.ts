import assert from "node:assert/strict";
import { test } from "node:test";

import { CLOCK_SAMPLES, measureClockOffset } from "../src/clock.ts";

/** A device clock 2.5 s behind the server's, and round trips of the given lengths. */
function scenario(roundTrips: number[], skew = 2.5) {
  let device = 1_000;
  const trips = [...roundTrips];
  return {
    deviceTime: () => device,
    serverTime: async () => {
      const trip = trips.shift() ?? 0;
      device += trip / 2; // there...
      const server = device + skew;
      device += trip / 2; // ...and back
      return server;
    },
  };
}

test("the offset is the server's clock minus the device's, read halfway through the request", async () => {
  const { serverTime, deviceTime } = scenario([0.2, 0.2, 0.2]);
  assert.equal(await measureClockOffset(serverTime, deviceTime), 2.5);
});

test("the fastest round trip is trusted, since a slow one hides where the server read its clock", async () => {
  let device = 0;
  // The slow trip spent 1.9 s on the way back alone, so halfway is wrong for it.
  const replies = [
    { there: 0.05, back: 1.9 },
    { there: 0.05, back: 0.05 },
    { there: 0.4, back: 0.1 },
  ];
  const serverTime = async () => {
    const { there, back } = replies.shift()!;
    device += there;
    const server = device + 10;
    device += back;
    return server;
  };
  const offset = await measureClockOffset(serverTime, () => device);
  assert.ok(Math.abs(offset - 10) < 0.001, `offset ${offset}`);
});

test("it takes three samples unless told otherwise", async () => {
  let calls = 0;
  await measureClockOffset(async () => (calls += 1), () => 0);
  assert.equal(calls, CLOCK_SAMPLES);
  await measureClockOffset(async () => (calls += 1), () => 0, 1);
  assert.equal(calls, CLOCK_SAMPLES + 1);
});
