import { EVENTS, LIVE_GAME, PLAYLIST, STREAMS } from "@commentary-sync/client/testing";
import { fireEvent, render, screen } from "@testing-library/react-native";

import App from "@/App";
import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { items } from "./_fakeSecureStore";
import { listenerApi } from "./_render";

function api() {
  return listenerApi()
    .on("GET", "/events?limit=100", { status: 200, body: EVENTS })
    .on("GET", "/streams?event_id=e-live&limit=100", { status: 200, body: STREAMS })
    .on("POST", "/streams/s-1/listener-playlist", { status: 200, body: PLAYLIST });
}

test("signed out, the app asks to sign in, then shows the games", async () => {
  api();
  await render(<App />);
  await fireEvent.changeText(screen.getByLabelText("Email"), "fan@example.com");
  await fireEvent.changeText(screen.getByLabelText("Password"), "correct horse battery");
  await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("header", { name: "Games" })).toBeOnTheScreen();
});

test("a listener picks a game and a commentator, listens, and goes back", async () => {
  api();
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
  await render(<App />);
  await fireEvent.press(await screen.findByRole("button", { name: LIVE_GAME.title }));
  await fireEvent.press(await screen.findByRole("button", { name: "Fan" }));
  expect(await screen.findByRole("header", { name: "Fan" })).toBeOnTheScreen();
  expect(await screen.findByText("Starting…")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: LIVE_GAME.title })).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByRole("header", { name: "Games" })).toBeOnTheScreen();
});

test("while a stored sign-in is being checked, the app waits", async () => {
  api();
  globalThis.fetch = () => new Promise<Response>(() => undefined); // the API never answers
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
  await render(<App />);
  expect(screen.getByLabelText("Signing in")).toBeOnTheScreen();
});
