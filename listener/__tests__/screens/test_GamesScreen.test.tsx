import { EVENTS, LIVE_GAME } from "@commentary-sync/client/testing";
import { fireEvent, screen } from "@testing-library/react-native";

import { GamesScreen } from "@/screens/GamesScreen";
import { listenerApi, renderSignedIn } from "../_render";

const LATER = { ...LIVE_GAME, id: "e-later", title: "Lakers at Celtics", league: "nba", status: "scheduled", networks: [] };
const OVER = { ...LIVE_GAME, id: "e-over", title: "Bears at Packers", status: "final" };
const GAMES = { ...EVENTS, items: [LIVE_GAME, LATER, OVER] };

test("lists the games on now or coming up, live ones marked", async () => {
  listenerApi().on("GET", "/events?limit=100", { status: 200, body: GAMES });
  await renderSignedIn(<GamesScreen onPick={jest.fn()} />);
  expect(await screen.findByRole("button", { name: LIVE_GAME.title })).toBeOnTheScreen();
  expect(screen.getByRole("button", { name: "Lakers at Celtics" })).toBeOnTheScreen();
  expect(screen.queryByText("Bears at Packers")).toBeNull();
  expect(screen.getAllByText("LIVE")).toHaveLength(1);
  expect(screen.getByText(/^NFL · .* · CBS$/)).toBeOnTheScreen();
});

test("picking a game opens it", async () => {
  listenerApi().on("GET", "/events?limit=100", { status: 200, body: GAMES });
  const onPick = jest.fn();
  await renderSignedIn(<GamesScreen onPick={onPick} />);
  await fireEvent.press(await screen.findByRole("button", { name: "Lakers at Celtics" }));
  expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: "e-later" }));
});

test("no games says so", async () => {
  listenerApi().on("GET", "/events?limit=100", { status: 200, body: { ...EVENTS, items: [OVER] } });
  await renderSignedIn(<GamesScreen onPick={jest.fn()} />);
  expect(await screen.findByText("No games on or coming up.")).toBeOnTheScreen();
});

test("the API's failure is explained", async () => {
  listenerApi().on("GET", "/events?limit=100", { status: 503, body: { detail: "Service unavailable" } });
  await renderSignedIn(<GamesScreen onPick={jest.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
});

test("signing out", async () => {
  const fake = listenerApi().on("GET", "/events?limit=100", { status: 200, body: GAMES });
  await renderSignedIn(<GamesScreen onPick={jest.fn()} />);
  await screen.findByRole("button", { name: LIVE_GAME.title });
  await fireEvent.press(screen.getByRole("button", { name: "Sign out" }));
  expect(fake.paths()).toContain("POST /auth/logout");
});
