import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Studio from "@/components/Studio";
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

async function endStream() {
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, end it" }));
}

async function readyToGoLive() {
  await userEvent.click(await screen.findByLabelText(/Houston Texans at Jacksonville Jaguars/));
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
  expect(await screen.findByText("Listeners can hear you")).toBeInTheDocument();
  expect(control.rooms[0]!.published[0]!.track).toBe(media.opened[0]!.track);
  // On air, the setup is gone: the game, LIVE, and the listeners' sync instead.
  expect(screen.getByRole("heading", { name: "Houston Texans at Jacksonville Jaguars" })).toBeInTheDocument();
  expect(screen.queryAllByRole("radio")).toEqual([]); // no game picker
  expect(screen.queryByLabelText("Microphone")).toBeNull();
  expect(await screen.findByText("9 of 11")).toBeInTheDocument();
  await endStream();
  expect(await screen.findByRole("button", { name: "Go live" })).toBeInTheDocument();
  expect(fake.paths()).toContain("POST /streams/s-1/end");
});

test("asks before leaving the page while live, and not after", async () => {
  renderSignedIn(<Studio />);
  await readyToGoLive();
  const leave = () => fireEvent(window, new Event("beforeunload", { cancelable: true }));
  expect(leave()).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: "Go live" }));
  await screen.findByText("Listeners can hear you");
  expect(leave()).toBe(false); // prevented: the browser asks
  await endStream();
  await screen.findByRole("button", { name: "Go live" });
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
  expect(screen.getByRole("heading", { name: "Your stream" })).toBeInTheDocument(); // its game isn't loaded after a reload
  await waitFor(() => expect(resume).toBeEnabled()); // once the mic is open
  await userEvent.click(resume);
  expect(await screen.findByText("Listeners can hear you")).toBeInTheDocument();
  expect(fake.paths()).not.toContain("POST /streams");
});

test("Go live says what's missing until a game is picked", async () => {
  renderSignedIn(<Studio />);
  expect(await screen.findByText("Pick the game you're watching first.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Go live" })).toBeDisabled();
});

test("without the microphone, Go live says to allow it", async () => {
  media.failure = "NotAllowedError";
  renderSignedIn(<Studio />);
  await userEvent.click(await screen.findByLabelText(/Houston Texans at Jacksonville Jaguars/));
  expect(await screen.findByText("Allow the microphone first.")).toBeInTheDocument();
});
