import { LIVE_GAME, STREAM, STREAMS } from "@commentary-sync/client/testing";
import { fireEvent, screen } from "@testing-library/react-native";

import { CommentatorsScreen } from "@/screens/CommentatorsScreen";
import { listenerApi, renderSignedIn } from "../_render";

const GAME = { ...LIVE_GAME, league: "nfl" as const, status: "live" as const };
const ROUTE = "/streams?event_id=e-live&limit=100";

test("lists who is commentating the game", async () => {
  listenerApi().on("GET", ROUTE, { status: 200, body: STREAMS });
  const onPick = jest.fn();
  await renderSignedIn(<CommentatorsScreen game={GAME} onPick={onPick} onBack={jest.fn()} />);
  expect(screen.getByRole("header", { name: GAME.title })).toBeOnTheScreen();
  await fireEvent.press(await screen.findByRole("button", { name: "Fan" }));
  expect(screen.getByText("@fan_cast · 3 listening")).toBeOnTheScreen();
  expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: STREAM.id }));
});

test("nobody yet says so", async () => {
  listenerApi().on("GET", ROUTE, { status: 200, body: { ...STREAMS, items: [] } });
  await renderSignedIn(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByText(/Nobody is commentating this game yet/)).toBeOnTheScreen();
});

test("a failure is explained", async () => {
  listenerApi().on("GET", ROUTE, { status: 500 });
  await renderSignedIn(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong; try again.");
});

test("when the API can't count listeners, just the handle", async () => {
  listenerApi().on("GET", ROUTE, { status: 200, body: { ...STREAMS, items: [{ ...STREAM, listeners: null }] } });
  await renderSignedIn(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByText("@fan_cast")).toBeOnTheScreen();
});
