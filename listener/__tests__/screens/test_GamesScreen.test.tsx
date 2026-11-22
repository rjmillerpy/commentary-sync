import { EVENTS, LIVE_GAME, STREAMS } from "@commentary-sync/client/testing";
import { fireEvent, screen } from "@testing-library/react-native";

import { GamesScreen } from "@/screens/GamesScreen";
import { listenerApi, renderWithAccess } from "../_render";

const LATER = { ...LIVE_GAME, id: "e-later", title: "Lakers at Celtics", league: "nba", status: "scheduled", networks: [] };
const OVER = { ...LIVE_GAME, id: "e-over", title: "Bears at Packers", status: "final" };
const GAMES = { ...EVENTS, items: [LATER, LIVE_GAME, OVER] };

function api(events: object = GAMES) {
  return listenerApi()
    .on("GET", "/events?limit=100", { status: 200, body: events })
    .on("GET", "/streams?limit=100", { status: 200, body: STREAMS });
}

test("games with commentary come first, with how many; then the rest; finished games aren't there", async () => {
  api();
  await renderWithAccess(<GamesScreen onPick={jest.fn()} />);
  expect(await screen.findByText("Commentary live now")).toBeOnTheScreen();
  const rows = screen.getAllByRole("button").filter((button) => /at/.test(String(button.props.accessibilityLabel)));
  expect(rows.map((row) => row.props.accessibilityLabel)).toEqual([
    expect.stringMatching(new RegExp(`^${LIVE_GAME.title}, 1 commentator live, NFL · .* · CBS, live$`)),
    expect.stringMatching(/^Lakers at Celtics, No commentary yet, NBA · /),
  ]);
  expect(screen.getByText("Other games")).toBeOnTheScreen();
  expect(screen.queryByText("Bears at Packers")).toBeNull();
});

test("picking a game opens it", async () => {
  api();
  const onPick = jest.fn();
  await renderWithAccess(<GamesScreen onPick={onPick} />);
  await fireEvent.press(await screen.findByRole("button", { name: /^Lakers at Celtics/ }));
  expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: "e-later" }));
});

test("while loading, placeholders, never a blank screen (UI rule 8)", async () => {
  api();
  globalThis.fetch = () => new Promise<Response>(() => undefined); // the API never answers
  await renderWithAccess(<GamesScreen onPick={jest.fn()} />);
  expect(screen.getByLabelText("Loading")).toBeOnTheScreen();
});

test("with no games, it says so", async () => {
  api({ ...EVENTS, items: [OVER] });
  await renderWithAccess(<GamesScreen onPick={jest.fn()} />);
  expect(await screen.findByText("No games on or coming up in the next few days.")).toBeOnTheScreen();
});

test("a failure says what happened, and Try again tries again", async () => {
  const fake = listenerApi()
    .on("GET", "/events?limit=100", { status: 503, body: { detail: "Service unavailable" } })
    .on("GET", "/streams?limit=100", { status: 200, body: STREAMS });
  await renderWithAccess(<GamesScreen onPick={jest.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the games: Service unavailable");
  fake.on("GET", "/events?limit=100", { status: 200, body: GAMES });
  await fireEvent.press(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Commentary live now")).toBeOnTheScreen();
});

test("Refresh is a button, not only a pull (UI rule 5.2)", async () => {
  const fake = api();
  await renderWithAccess(<GamesScreen onPick={jest.fn()} />);
  await screen.findByText("Commentary live now");
  await fireEvent.press(screen.getByRole("button", { name: "Refresh" }));
  expect(fake.paths().filter((path) => path === "GET /events?limit=100").length).toBeGreaterThanOrEqual(2);
});
