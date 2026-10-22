import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Studio from "@/components/Studio";
import { toPower } from "@/lib/gate";
import { QUIET_SECONDS, TALK_SECONDS } from "@/lib/tvCheck";
import { control } from "../_fakeLiveKit";
import { type FakeApi, OWN_LIVE_STREAMS, STILL_LIVE, studioApi } from "../_fakeApi";
import { type FakeMedia, installMedia } from "../_fakeMedia";
import { MemoryStore } from "../_memoryStore";
import { renderSignedIn, renderSignedOut } from "../_render";

jest.mock("livekit-client", () => jest.requireActual("../_fakeLiveKit").liveKitModule);

let fake: FakeApi;
let media: FakeMedia;

beforeEach(() => {
  control.reset();
  fake = studioApi();
  media = installMedia();
});

/** Runs the TV check with the TV and the voice at these levels (dBFS). */
async function checkTv(tvDb: number, voiceDb: number) {
  const start = await screen.findByRole("button", { name: /Start the TV check|Check again/ });
  await waitFor(() => expect(start).toBeEnabled());
  jest.useFakeTimers();
  fireEvent.click(start);
  const gate = media.worklets.filter((node) => node.name === "voice-gate").at(-1)!;
  act(() => {
    gate.post({ power: toPower(tvDb), openShare: 0 });
    jest.advanceTimersByTime(QUIET_SECONDS * 1_000);
    gate.post({ power: toPower(voiceDb), openShare: 1 });
    jest.advanceTimersByTime(TALK_SECONDS * 1_000);
  });
  jest.useRealTimers();
}

async function readyToGoLive() {
  await userEvent.click(await screen.findByLabelText(/Houston Texans at Jacksonville Jaguars/));
  await checkTv(-50, -20);
  await waitFor(() => expect(screen.getByRole("button", { name: "Go live" })).toBeEnabled());
}

test("smoke: sign in, pick a game, go live and end", async () => {
  renderSignedOut(<Studio />);
  await userEvent.type(screen.getByLabelText("Email"), "fan@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("@fan_cast")).toBeInTheDocument();
  await readyToGoLive();
  await userEvent.click(screen.getByRole("button", { name: "Go live" }));
  expect(await screen.findByText("Live: listeners can hear you")).toBeInTheDocument();
  // On air: the gate's output, never the raw microphone.
  expect(control.rooms[0]!.published[0]!.track).toBe(media.destinations[0]!.track);
  expect(screen.getByRole("button", { name: "Check again" })).toBeDisabled();
  expect(screen.getByLabelText(/Houston Texans/)).toBeDisabled();
  expect(screen.getByLabelText("Microphone")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  expect(await screen.findByText("Off air")).toBeInTheDocument();
  expect(fake.paths()).toContain("POST /streams/s-1/end");
});

test("asks before leaving the page while live, and not after", async () => {
  renderSignedIn(<Studio />);
  await readyToGoLive();
  const leave = () => fireEvent(window, new Event("beforeunload", { cancelable: true }));
  expect(leave()).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: "Go live" }));
  await screen.findByText("Live: listeners can hear you");
  expect(leave()).toBe(false); // prevented: the browser asks
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  await screen.findByText("Off air");
  expect(leave()).toBe(true);
});

test("shows that it is signing back in after a reload", () => {
  renderSignedIn(<Studio />);
  expect(screen.getByText("Signing you back in…")).toBeInTheDocument();
});

test("signing out returns to the sign-in form", async () => {
  const store = new MemoryStore("refresh-1");
  renderSignedOut(<Studio />, store);
  await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("heading", { name: "Sign in to the studio" })).toBeInTheDocument();
  expect(store.token).toBeNull();
});


test("after a reload mid-broadcast, the studio offers to resume on the same game", async () => {
  fake.on("GET", OWN_LIVE_STREAMS, { status: 200, body: STILL_LIVE });
  renderSignedIn(<Studio />);
  const resume = await screen.findByRole("button", { name: "Resume" });
  expect(screen.getByLabelText(/Houston Texans/)).toBeChecked();
  expect(resume).toBeDisabled(); // a reload needs a new TV check
  await checkTv(-50, -20);
  await waitFor(() => expect(resume).toBeEnabled());
  await userEvent.click(resume);
  expect(await screen.findByText("Live: listeners can hear you")).toBeInTheDocument();
  expect(fake.paths()).not.toContain("POST /streams");
});

test("going live waits for a TV check the TV passes", async () => {
  renderSignedIn(<Studio />);
  await userEvent.click(await screen.findByLabelText(/Houston Texans at Jacksonville Jaguars/));
  const goLive = screen.getByRole("button", { name: "Go live" });
  expect(goLive).toBeDisabled();
  await checkTv(-25, -20);
  expect(await screen.findByText(/would go out to listeners/)).toBeInTheDocument();
  expect(goLive).toBeDisabled();
  await checkTv(-50, -20);
  await waitFor(() => expect(goLive).toBeEnabled());
});
