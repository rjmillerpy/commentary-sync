import { EVENTS, LIVE_GAME, PLAYLIST, STREAMS } from "@commentary-sync/client/testing";
import { fireEvent, render, screen } from "@testing-library/react-native";

import App from "@/App";
import { listenerApi } from "./_render";

function api() {
  return listenerApi()
    .on("GET", "/events?limit=100", { status: 200, body: EVENTS })
    .on("GET", "/streams?limit=100", { status: 200, body: STREAMS })
    .on("GET", "/streams?event_id=e-live&limit=100", { status: 200, body: STREAMS })
    .on("POST", "/streams/s-1/listener-playlist", { status: 200, body: PLAYLIST });
}

test("no account needed: it opens on the games, and three screens later the listener is listening", async () => {
  const fake = api();
  await render(<App />);
  expect(screen.getByRole("header", { name: "Games" })).toBeOnTheScreen();
  await fireEvent.press(await screen.findByRole("button", { name: new RegExp(`^${LIVE_GAME.title}`) }));
  await fireEvent.press(await screen.findByRole("button", { name: /^Fan,/ }));
  expect(await screen.findByRole("header", { name: "Fan" })).toBeOnTheScreen();
  expect(await screen.findByTestId("sync-status")).toBeOnTheScreen();
  expect(fake.paths()).toContain("POST /auth/guest"); // a guest, not a sign-in
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: LIVE_GAME.title })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: "Games" })).toBeOnTheScreen();
});
