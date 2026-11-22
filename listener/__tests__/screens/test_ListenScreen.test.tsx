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
import { listenerApi, renderWithAccess } from "../_render";
import { ENDED_STREAM_FIXTURE } from "../_streams";

const GAME = { ...LIVE_GAME, league: "nfl" as const, status: "live" as const };
const STREAM_ROW = { ...STREAM, status: "live" as const };
const ROUTE = "/streams/s-1/listener-playlist";

// Opening a stream syncs for real: 10 s of audio resampled and turned into
// features in JavaScript, which takes seconds of CPU on a busy machine.
jest.setTimeout(30_000);

beforeEach(() => {
  jest.useFakeTimers();
  microphone.feed = Float32Array.from({ length: RECORDING_SECONDS * 48_000 }, (_, index) => Math.sin(index / 7) * ((index >> 12) % 3));
});
afterEach(() => jest.useRealTimers());

const advance = (ms: number) =>
  act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });

function api() {
  return listenerApi()
    .on("POST", ROUTE, { status: 200, body: PLAYLIST })
    .on("POST", "/streams/s-1/listening", { status: 204 })
    .on("GET", "/clock", { status: 200, body: { now: Date.now() / 1000 } })
    .on("POST", "/streams/s-1/sync", { status: 200, body: SYNC_MATCHED });
}

async function renderListening(onBack = jest.fn()) {
  await renderWithAccess(<ListenScreen game={GAME} stream={STREAM_ROW} onBack={onBack} />);
  return onBack;
}

const status = () => screen.getByTestId("sync-status");

test("smoke: opening it syncs with the TV by itself, then plays at that delay and says it's synced", async () => {
  api();
  await renderListening();
  expect(screen.getByRole("header", { name: "Fan" })).toBeOnTheScreen();
  expect(screen.getByText(GAME.title)).toBeOnTheScreen();
  expect(await screen.findByText("Listening to your TV…")).toBeOnTheScreen();
  Object.assign(latestPlayer(), { currentTime: 120, currentOffsetFromLive: 10 });
  await advance(RECORDING_SECONDS * 1_000);
  await advance(TICK_MS);
  await advance(TICK_MS);
  expect(status()).toHaveTextContent(/Synced with your TV$/);
  expect(latestPlayer().playing).toBe(true);
});

test("waits for the commentator's audio", async () => {
  listenerApi().on("POST", ROUTE, { status: 409, body: { detail: NO_HLS_YET_DETAIL } });
  await renderListening();
  expect(await screen.findByText("Waiting for Fan's audio to start…")).toBeOnTheScreen();
});

test("a playlist that can't be had says why, with one way out", async () => {
  listenerApi().on("POST", ROUTE, { status: 409, body: { detail: "This stream has already ended" } });
  const onBack = await renderListening();
  expect(await screen.findByRole("alert")).toHaveTextContent("Can't play this commentary: This stream has already ended");
  await fireEvent.press(screen.getByRole("button", { name: "Pick another commentator" }));
  expect(onBack).toHaveBeenCalled();
});

test("with no connection, the status says it's reconnecting, and why", async () => {
  api();
  await renderListening();
  await act(() => setOnline(false));
  expect(status()).toHaveTextContent(/Reconnecting….*No connection/);
  await act(() => setOnline(true));
  expect(status()).not.toHaveTextContent(/Reconnecting/);
});

test("pausing shows how far behind, and the status jumps back", async () => {
  api();
  await renderListening();
  await advance(RECORDING_SECONDS * 1_000 + TICK_MS);
  Object.assign(latestPlayer(), { currentTime: 120, currentOffsetFromLive: 23.5 });
  await fireEvent.press(screen.getByRole("button", { name: "Pause commentary" }));
  latestPlayer().advance(42);
  await advance(TICK_MS);
  expect(status()).toHaveTextContent(/You're 0:42 behind · Jump back in$/);
  await fireEvent.press(status());
  expect(screen.getByRole("button", { name: "Pause commentary" })).toBeOnTheScreen();
  expect(latestPlayer().playing).toBe(true);
});

test("fine-tune and volume are right there; sync details are folded away", async () => {
  api();
  await renderListening();
  await fireEvent.press(screen.getByRole("button", { name: "Hear the commentary a tenth of a second later" }));
  expect(screen.getByLabelText("Fine-tune +0.1 s")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Quieter" }));
  expect(latestPlayer().volume).toBe(0.9);
  expect(screen.queryByText("Sync details")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "More options" }));
  expect(screen.getByText("Sync details")).toBeOnTheScreen();
});

test("when the commentator ends the stream, the listener is told, with a way on", async () => {
  api().on("GET", "/streams/s-1", { status: 200, body: ENDED_STREAM_FIXTURE });
  const onBack = await renderListening();
  await advance(STREAM_CHECK_MS);
  expect(screen.getByText("Fan has ended the stream.")).toBeOnTheScreen();
  expect(screen.queryByTestId("sync-status")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Pick another commentator" }));
  expect(onBack).toHaveBeenCalled();
});

test("while the commentary plays, the app checks in as a listener", async () => {
  const fake = api();
  await renderListening();
  await advance(RECORDING_SECONDS * 1_000 + TICK_MS);
  Object.assign(latestPlayer(), { currentTime: 120, currentOffsetFromLive: 23.5 });
  await advance(TICK_MS);
  expect(fake.paths()).toContain("POST /streams/s-1/listening");
});
