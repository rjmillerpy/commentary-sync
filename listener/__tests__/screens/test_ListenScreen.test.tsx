import { NO_HLS_YET_DETAIL } from "@commentary-sync/client/api";
import { LIVE_GAME, PLAYLIST, STREAM, SYNC_MATCHED } from "@commentary-sync/client/testing";
import { act, fireEvent, screen } from "@testing-library/react-native";

import { TICK_MS } from "@/hooks/useDelayedPlayback";
import { STREAM_CHECK_MS } from "@/hooks/useStreamEnded";
import { RECORDING_SECONDS } from "@/lib/tvSync";
import { ListenScreen } from "@/screens/ListenScreen";
import { microphone } from "../_fakeAudio";
import { setOnline } from "../_fakeNetwork";
import { latestPlayer } from "../_fakeVideo";
import { listenerApi, renderSignedIn } from "../_render";
import { ENDED_STREAM_FIXTURE } from "../_streams";

const GAME = { ...LIVE_GAME, league: "nfl" as const, status: "live" as const };
const STREAM_ROW = { ...STREAM, status: "live" as const };
const ROUTE = "/streams/s-1/listener-playlist";

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

async function tick(): Promise<void> {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(TICK_MS);
  });
}

async function renderListening() {
  await renderSignedIn(<ListenScreen game={GAME} stream={STREAM_ROW} onBack={jest.fn()} />);
}

test("waits for the commentator's audio", async () => {
  listenerApi().on("POST", ROUTE, { status: 409, body: { detail: NO_HLS_YET_DETAIL } });
  await renderListening();
  expect(await screen.findByText("Waiting for Fan's audio…")).toBeOnTheScreen();
  expect(screen.getByText(GAME.title)).toBeOnTheScreen();
});

test("plays at the chosen delay, and follows a new one", async () => {
  listenerApi().on("POST", ROUTE, { status: 200, body: PLAYLIST });
  await renderListening();
  expect(await screen.findByText("Starting…")).toBeOnTheScreen();
  Object.assign(latestPlayer(), { currentTime: 120, currentOffsetFromLive: 10 });
  await tick();
  expect(screen.getByText("Playing 10.0 s behind live")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "More delay, 5 seconds" }));
  await tick();
  expect(latestPlayer().seeks).toEqual([-5]);
  expect(screen.getByLabelText("Delay 15.0 s")).toBeOnTheScreen();
});

test("says when it is building up the delay", async () => {
  listenerApi().on("POST", ROUTE, { status: 200, body: PLAYLIST });
  await renderListening();
  await screen.findByText("Starting…");
  Object.assign(latestPlayer(), { currentTime: 1, currentOffsetFromLive: 3 });
  await tick();
  expect(screen.getByText("Building up the delay: 3.0 s of 10.0 s")).toBeOnTheScreen();
});

test("an ended stream is explained", async () => {
  listenerApi().on("POST", ROUTE, { status: 409, body: { detail: "This stream has already ended" } });
  await renderListening();
  expect(await screen.findByRole("alert")).toHaveTextContent("This stream has already ended");
});

test("a player failure says it is reconnecting, not that it's over", async () => {
  listenerApi().on("POST", ROUTE, { status: 200, body: PLAYLIST });
  await renderListening();
  await screen.findByText("Starting…");
  Object.assign(latestPlayer(), { status: "error", keepsFailing: true });
  await tick();
  expect(screen.getByText(/^Reconnecting… the commentary picks up again at the same delay/)).toBeOnTheScreen();
});

test("with no connection, the listener is told it will pick up again", async () => {
  listenerApi().on("POST", ROUTE, { status: 200, body: PLAYLIST });
  await renderListening();
  await act(() => setOnline(false));
  expect(screen.getByRole("alert")).toHaveTextContent(/No connection\. The commentary picks up again at the same delay/);
  await act(() => setOnline(true));
  expect(screen.queryByText(/No connection/)).toBeNull();
});

test("syncing with the TV pauses the commentary while it listens, then sets the delay", async () => {
  listenerApi()
    .on("POST", ROUTE, { status: 200, body: PLAYLIST })
    .on("GET", "/clock", { status: 200, body: { now: Date.now() / 1000 } })
    .on("POST", "/streams/s-1/sync", { status: 200, body: SYNC_MATCHED });
  microphone.feed = Float32Array.from({ length: RECORDING_SECONDS * 48_000 }, (_, index) => Math.sin(index / 7) * ((index >> 12) % 3));
  await renderListening();
  await screen.findByText("Starting…");
  const player = latestPlayer();
  await fireEvent.press(screen.getByRole("button", { name: "Sync with my TV" }));
  expect(await screen.findByText(/Listening to your TV/)).toBeOnTheScreen();
  expect(player.playing).toBe(false);
  await act(async () => {
    await jest.advanceTimersByTimeAsync(RECORDING_SECONDS * 1_000);
  });
  expect(await screen.findByText(/Synced: the commentary now runs 23.5 s behind/)).toBeOnTheScreen();
  expect(screen.getByLabelText("Delay 23.5 s")).toBeOnTheScreen();
  expect(player.playing).toBe(true);
});

test("when the commentator ends the stream, the listener is told", async () => {
  listenerApi()
    .on("POST", ROUTE, { status: 200, body: PLAYLIST })
    .on("GET", "/streams/s-1", { status: 200, body: ENDED_STREAM_FIXTURE });
  await renderListening();
  await act(async () => {
    await jest.advanceTimersByTimeAsync(STREAM_CHECK_MS);
  });
  expect(screen.getByText("Fan has ended the stream.")).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Sync with my TV" })).toBeNull();
});

test("while the commentary plays, the app checks in as a listener", async () => {
  const fake = listenerApi()
    .on("POST", ROUTE, { status: 200, body: PLAYLIST })
    .on("POST", "/streams/s-1/listening", { status: 204 });
  await renderListening();
  await screen.findByText("Starting…");
  Object.assign(latestPlayer(), { currentTime: 120, currentOffsetFromLive: 10 });
  await tick();
  expect(fake.paths()).toContain("POST /streams/s-1/listening");
});
