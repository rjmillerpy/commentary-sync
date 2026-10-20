import { act, renderHook, waitFor } from "@testing-library/react";

import { AUDIENCE_CHECK_MS, useAudience } from "@/hooks/useAudience";
import { FakeApi, STREAM } from "../_fakeApi";

afterEach(() => jest.useRealTimers());

test("not live: nothing is checked", () => {
  const fake = new FakeApi().install();
  const { result } = renderHook(() => useAudience(null));
  expect(result.current).toBeNull();
  expect(fake.requests).toEqual([]);
});

test("live: the count is read at once and every 10 seconds", async () => {
  jest.useFakeTimers();
  const fake = new FakeApi()
    .on("GET", "/streams/s-1", { status: 200, body: { ...STREAM, listeners: 2 } }, { status: 200, body: { ...STREAM, listeners: 5 } })
    .install();
  const { result } = renderHook(() => useAudience("s-1"));
  await waitFor(() => expect(result.current).toBe(2));
  await act(async () => {
    await jest.advanceTimersByTimeAsync(AUDIENCE_CHECK_MS);
  });
  expect(result.current).toBe(5);
  expect(fake.paths()).toEqual(["GET /streams/s-1", "GET /streams/s-1"]);
});

test("a failed check keeps the last count", async () => {
  jest.useFakeTimers();
  const fake = new FakeApi().on("GET", "/streams/s-1", { status: 200, body: { ...STREAM, listeners: 4 } }).install();
  const { result } = renderHook(() => useAudience("s-1"));
  await waitFor(() => expect(result.current).toBe(4));
  fake.offline = true;
  await act(async () => {
    await jest.advanceTimersByTimeAsync(AUDIENCE_CHECK_MS);
  });
  expect(result.current).toBe(4);
});

test("going off air stops the checks and forgets the count (rule 71)", async () => {
  jest.useFakeTimers();
  const fake = new FakeApi().on("GET", "/streams/s-1", { status: 200, body: { ...STREAM, listeners: 4 } }).install();
  const { result, rerender } = renderHook(({ id }) => useAudience(id), { initialProps: { id: "s-1" as string | null } });
  await waitFor(() => expect(result.current).toBe(4));
  rerender({ id: null });
  expect(result.current).toBeNull();
  const asked = fake.requests.length;
  await act(async () => {
    await jest.advanceTimersByTimeAsync(AUDIENCE_CHECK_MS * 3);
  });
  expect(fake.requests).toHaveLength(asked);
});
