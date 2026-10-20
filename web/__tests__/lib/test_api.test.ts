import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import { EVENTS, FakeApi } from "../_fakeApi";

// The calls themselves are tested with the shared client (client/test).
// Here: the studio's binding of them.

let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi().install();
});

test("calls go to the studio's API address", async () => {
  fake.on("GET", "/events?limit=100", { status: 200, body: EVENTS });
  await api.upcomingEvents();
  expect(fake.fetch.mock.calls[0]![0]).toBe("http://localhost:8000/events?limit=100");
});

test("each call is given a timeout", async () => {
  fake.on("GET", "/events?limit=100", { status: 200, body: EVENTS });
  await api.upcomingEvents();
  const init = fake.fetch.mock.calls[0]![1] as RequestInit;
  expect(init.signal).toBeInstanceOf(AbortSignal);
});

test("every endpoint the studio uses is bound", () => {
  const studioCalls = [
    api.register,
    api.login,
    api.refresh,
    api.logout,
    api.myCommentatorProfile,
    api.becomeCommentator,
    api.upcomingEvents,
    api.goLive,
    api.liveStreamOf,
    api.getStream,
    api.endStream,
    api.publisherToken,
  ];
  expect(studioCalls.every((call) => typeof call === "function")).toBe(true);
});

test("failures are the shared client's ApiError", async () => {
  fake.offline = true;
  await expect(api.upcomingEvents()).rejects.toBeInstanceOf(ApiError);
});
