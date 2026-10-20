import { renderHook, waitFor } from "@testing-library/react";

import { useReference } from "@/hooks/useReference";
import { CHUNK_SECONDS, REFERENCE_SAMPLE_RATE } from "@/lib/reference";
import { Session } from "@/lib/session";
import { FakeApi, PAIR } from "../_fakeApi";
import { type FakeMedia, installMedia } from "../_fakeMedia";
import { MemoryStore } from "../_memoryStore";

let media: FakeMedia;
let fake: FakeApi;
let session: Session;

beforeEach(async () => {
  media = installMedia();
  fake = new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("GET", "/clock", { status: 200, body: { now: 1_000_000 } })
    .on("POST", "/streams/s-1/reference", { status: 204 })
    .install();
  session = new Session(new MemoryStore());
  await session.signIn("fan@example.com", "pw");
});

const authorized = <T,>(action: (token: string) => Promise<T>) => session.authorized(action);

test("not live: nothing is recorded", () => {
  const { result } = renderHook(() => useReference({ authorized }, null, null));
  expect(result.current).toBe("off");
  expect(media.opened).toHaveLength(0);
});

test("live: the room is recorded raw and sent in server time", async () => {
  const { result } = renderHook(() => useReference({ authorized }, "s-1", "usb-mic"));
  await waitFor(() => expect(result.current).toBe("on"));
  expect(media.constraints[0]).toEqual({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, deviceId: { exact: "usb-mic" } },
    video: false,
  });
  media.worklets[0]!.deliver(0, new Float32Array(CHUNK_SECONDS * REFERENCE_SAMPLE_RATE));
  await waitFor(() => expect(fake.paths().some((path) => path.startsWith("POST /streams/s-1/reference?"))).toBe(true));
  const sent = fake.requests.find((request) => request.path.startsWith("/streams/s-1/reference"))!;
  const capturedAt = Number(new URL(`http://x${sent.path}`).searchParams.get("captured_at"));
  // The first sample was captured just now; the server's clock reads 1 000 000 s now.
  expect(Math.abs(capturedAt - 1_000_000)).toBeLessThan(5);
  expect(sent.authorization).toBe("Bearer access-1");
  expect(sent.body).toBeInstanceOf(Int16Array);
});

test("going off air stops the recording and frees the microphone (rule 71)", async () => {
  const { result, rerender } = renderHook(({ id }) => useReference({ authorized }, id, null), {
    initialProps: { id: "s-1" as string | null },
  });
  await waitFor(() => expect(result.current).toBe("on"));
  rerender({ id: null });
  expect(result.current).toBe("off");
  expect(media.opened[0]!.track.stop).toHaveBeenCalled();
  expect(media.contexts[0]!.closed).toBe(true);
});

test("a browser that won't open the microphone again leaves sync unavailable", async () => {
  media.failure = "NotReadableError";
  const { result } = renderHook(() => useReference({ authorized }, "s-1", null));
  await waitFor(() => expect(result.current).toBe("unavailable"));
});

test("leaving while it starts undoes the start", async () => {
  const { unmount } = renderHook(() => useReference({ authorized }, "s-1", null));
  unmount();
  await waitFor(() => expect(media.opened).toHaveLength(1));
  await waitFor(() => expect(media.opened[0]!.track.stop).toHaveBeenCalled());
});

test("a chunk the API refuses is skipped, not fatal", async () => {
  fake.on("POST", "/streams/s-1/reference", { status: 500 });
  const { result } = renderHook(() => useReference({ authorized }, "s-1", null));
  await waitFor(() => expect(result.current).toBe("on"));
  media.worklets[0]!.deliver(0, new Float32Array(CHUNK_SECONDS * REFERENCE_SAMPLE_RATE));
  await waitFor(() => expect(fake.paths().length).toBeGreaterThan(4));
  expect(result.current).toBe("on");
});
