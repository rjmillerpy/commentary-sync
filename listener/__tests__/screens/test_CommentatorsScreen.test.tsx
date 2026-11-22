import { LIVE_GAME, STREAM, STREAMS } from "@commentary-sync/client/testing";
import { fireEvent, screen } from "@testing-library/react-native";

import { CommentatorsScreen } from "@/screens/CommentatorsScreen";
import { listenerApi, renderWithAccess } from "../_render";

const GAME = { ...LIVE_GAME, league: "nfl" as const, status: "live" as const };
const ROUTE = "/streams?event_id=e-live&limit=100";

test("lists who is commentating the game, with their listeners", async () => {
  listenerApi().on("GET", ROUTE, { status: 200, body: STREAMS });
  const onPick = jest.fn();
  await renderWithAccess(<CommentatorsScreen game={GAME} onPick={onPick} onBack={jest.fn()} />);
  expect(screen.getByRole("header", { name: GAME.title })).toBeOnTheScreen();
  expect(screen.getByText("Pick a commentator")).toBeOnTheScreen();
  await fireEvent.press(await screen.findByRole("button", { name: "Fan, @fan_cast · 3 listeners, live" }));
  expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: STREAM.id }));
});

test("one listener reads as one", async () => {
  listenerApi().on("GET", ROUTE, { status: 200, body: { ...STREAMS, items: [{ ...STREAM, listeners: 1 }] } });
  await renderWithAccess(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByText("@fan_cast · 1 listener")).toBeOnTheScreen();
});

test("nobody yet says so, and offers to check again", async () => {
  const fake = listenerApi().on("GET", ROUTE, { status: 200, body: { ...STREAMS, items: [] } });
  await renderWithAccess(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByText("Nobody is commentating this game yet.")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Check again" }));
  expect(fake.paths().filter((path) => path === `GET ${ROUTE}`)).toHaveLength(2);
});

test("a failure is explained, with Try again", async () => {
  listenerApi().on("GET", ROUTE, { status: 500 });
  await renderWithAccess(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the commentators: Something went wrong; try again.");
  expect(screen.getByRole("button", { name: "Try again" })).toBeOnTheScreen();
});

test("when the API can't count listeners, just the handle", async () => {
  listenerApi().on("GET", ROUTE, { status: 200, body: { ...STREAMS, items: [{ ...STREAM, listeners: null }] } });
  await renderWithAccess(<CommentatorsScreen game={GAME} onPick={jest.fn()} onBack={jest.fn()} />);
  expect(await screen.findByText("@fan_cast")).toBeOnTheScreen();
});
