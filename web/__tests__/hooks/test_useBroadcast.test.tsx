import { act, renderHook, waitFor } from "@testing-library/react";

import { useBroadcast } from "@/hooks/useBroadcast";
import { Session } from "@/lib/session";
import { control } from "../_fakeLiveKit";
import { type FakeApi, OWN_LIVE_STREAMS, STILL_LIVE, studioApi } from "../_fakeApi";
import { MemoryStore } from "../_memoryStore";

jest.mock("livekit-client", () => jest.requireActual("../_fakeLiveKit").liveKitModule);

const microphone = { kind: "audio" } as MediaStreamTrack;
let fake: FakeApi;
let session: Session;

beforeEach(async () => {
  control.reset();
  fake = studioApi();
  session = new Session(new MemoryStore());
  await session.signIn("fan@example.com", "pw");
  fake.requests.length = 0;
});

function useStudioBroadcast() {
  return useBroadcast({ authorized: (action) => session.authorized(action) }, "fan_cast");
}

/** Rendered once the still-live check has answered, so its requests are done. */
async function renderBroadcast() {
  const rendered = renderHook(useStudioBroadcast);
  await waitFor(() => expect(fake.paths()).toContain(`GET ${OWN_LIVE_STREAMS}`));
  fake.requests.length = 0;
  return rendered;
}

test("going live creates the stream, gets a publisher token and sends the mic", async () => {
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  expect(fake.paths()).toEqual(["POST /streams", "POST /streams/s-1/publisher-token"]);
  expect(fake.requests[0]!.body).toEqual({ event_id: "e-live" });
  expect(control.rooms[0]!.connectedTo).toEqual({ url: "ws://localhost:7880/", token: "room-token" });
  expect(result.current.phase).toBe("live");
  expect(result.current.stream?.id).toBe("s-1");
});

test("ending leaves the room and ends the stream", async () => {
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  await act(() => result.current.end());
  expect(fake.paths().at(-1)).toBe("POST /streams/s-1/end");
  expect(control.rooms[0]!.disconnectedWith).toBe(false);
  expect(result.current).toMatchObject({ phase: "idle", stream: null, error: null });
});

test("ending before going live does nothing", async () => {
  const { result } = await renderBroadcast();
  await act(() => result.current.end());
  expect(fake.requests).toEqual([]);
});

test("the phase follows LiveKit reconnecting", async () => {
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  act(() => control.rooms[0]!.emit("reconnecting"));
  expect(result.current.phase).toBe("reconnecting");
  act(() => control.rooms[0]!.emit("reconnected"));
  expect(result.current.phase).toBe("live");
});

test("the API refusing to go live shows its reason", async () => {
  fake.on("POST", "/streams", { status: 409, body: { detail: "You are already live; end that stream first" } });
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  expect(result.current).toMatchObject({ phase: "idle", error: "You are already live; end that stream first" });
  expect(control.rooms).toEqual([]);
});

test("regression: audio failing to connect ends the stream it created", async () => {
  // Otherwise the commentator shows as live with no audio until the game ends.
  control.connectFailure = new Error("could not establish pc connection");
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  expect(fake.paths()).toContain("POST /streams/s-1/end");
  expect(result.current).toMatchObject({
    phase: "idle",
    stream: null,
    error: "Couldn't connect your audio. Check your connection and try again.",
  });
});

test("a failed clean-up is ignored: the API ends the stream itself later", async () => {
  fake.on("POST", "/streams/s-1/publisher-token", { status: 409, body: { detail: "This stream has already ended" } });
  fake.on("POST", "/streams/s-1/end", { status: 409, body: { detail: "This stream has already ended" } });
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  expect(result.current.error).toBe("This stream has already ended");
});

test("leaving the page stops sending", async () => {
  const { result, unmount } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  unmount();
  expect(control.rooms[0]!.handlers.size).toBe(0);
});


test("LiveKit giving up leaves the stream interrupted, to resume", async () => {
  const { result } = await renderBroadcast();
  await act(() => result.current.start("e-live", microphone));
  act(() => control.rooms[0]!.emit("disconnected"));
  expect(result.current.phase).toBe("interrupted");
  await act(() => result.current.resume(microphone));
  expect(result.current.phase).toBe("live");
  expect(control.rooms).toHaveLength(2);
  expect(control.rooms[0]!.disconnectedWith).toBe(false); // the old room is left first
});

describe("after a reload", () => {
  beforeEach(() => {
    fake.on("GET", OWN_LIVE_STREAMS, { status: 200, body: STILL_LIVE });
  });

  test("a stream left live is picked up, interrupted", async () => {
    const { result } = renderHook(useStudioBroadcast);
    await waitFor(() => expect(result.current.phase).toBe("interrupted"));
    expect(result.current.stream?.id).toBe("s-1");
  });

  test("resuming gets a new publisher token and sends the mic again", async () => {
    const { result } = renderHook(useStudioBroadcast);
    await waitFor(() => expect(result.current.phase).toBe("interrupted"));
    await act(() => result.current.resume(microphone));
    expect(fake.paths().at(-1)).toBe("POST /streams/s-1/publisher-token");
    expect(result.current.phase).toBe("live");
  });

  test("a stream the API ended meanwhile goes back to off air", async () => {
    fake.on("POST", "/streams/s-1/publisher-token", { status: 409, body: { detail: "This stream has already ended" } });
    const { result } = renderHook(useStudioBroadcast);
    await waitFor(() => expect(result.current.phase).toBe("interrupted"));
    await act(() => result.current.resume(microphone));
    expect(result.current).toMatchObject({ phase: "idle", stream: null, error: "This stream has already ended" });
  });

  test("audio failing to reconnect stays interrupted, to try again", async () => {
    control.connectFailure = new Error("no route");
    const { result } = renderHook(useStudioBroadcast);
    await waitFor(() => expect(result.current.phase).toBe("interrupted"));
    await act(() => result.current.resume(microphone));
    expect(result.current).toMatchObject({ phase: "interrupted", error: "Couldn't connect your audio. Check your connection and try again." });
    expect(result.current.stream?.id).toBe("s-1");
  });

  test("unmounting before the check answers changes nothing", async () => {
    const { result, unmount } = renderHook(useStudioBroadcast);
    unmount();
    await waitFor(() => expect(fake.paths()).toContain(`GET ${OWN_LIVE_STREAMS}`));
    expect(result.current.phase).toBe("idle");
  });
});

test("the still-live check failing leaves the studio off air", async () => {
  fake.offline = true;
  const { result } = renderHook(useStudioBroadcast);
  await waitFor(() => expect(fake.fetch).toHaveBeenCalled());
  expect(result.current.phase).toBe("idle");
});

test("resuming with nothing to resume does nothing", async () => {
  const { result } = await renderBroadcast();
  await act(() => result.current.resume(microphone));
  expect(fake.requests).toEqual([]);
});
