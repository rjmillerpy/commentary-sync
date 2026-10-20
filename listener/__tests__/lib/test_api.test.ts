import { EVENTS, FakeApi } from "@commentary-sync/client/testing";

import { api } from "@/lib/api";

test("calls go to the configured API address", async () => {
  const fake = new FakeApi().on("GET", "/events?limit=100", { status: 200, body: EVENTS }).install();
  const fetchSpy = jest.spyOn(globalThis, "fetch");
  await api.upcomingEvents();
  expect(fetchSpy.mock.calls[0]?.[0]).toBe("http://localhost:8000/events?limit=100");
  expect(fake.paths()).toEqual(["GET /events?limit=100"]);
});
