import type { SportsEvent, Stream } from "@commentary-sync/client/schema";
import { LIVE_GAME, STREAM } from "@commentary-sync/client/testing";

import { commentatorCount, sectionGames, whenAndWhere } from "@/lib/games";

const NFL_GAME = LIVE_GAME as SportsEvent;
const game = (id: string, status: SportsEvent["status"]): SportsEvent => ({ ...NFL_GAME, id, status });
const streamOn = (eventId: string, id: string): Stream => ({ ...(STREAM as Stream), id, event_id: eventId });

test("games with commentary come first, busiest first; finished games are left out", () => {
  const games = [game("quiet", "scheduled"), game("one", "live"), game("two", "live"), game("over", "final")];
  const live = [streamOn("two", "a"), streamOn("one", "b"), streamOn("two", "c"), streamOn("over", "d")];
  const { withCommentary, others } = sectionGames(games, live);
  expect(withCommentary.map((entry) => [entry.game.id, entry.commentators])).toEqual([["two", 2], ["one", 1]]);
  expect(others.map((entry) => entry.game.id)).toEqual(["quiet"]);
});

test.each([
  [0, "No commentary yet"],
  [1, "1 commentator live"],
  [3, "3 commentators live"],
])("%s commentators read as %s", (count, text) => {
  expect(commentatorCount(count)).toBe(text);
});

test("when and where: the league, the start, and the networks", () => {
  const text = whenAndWhere({ ...NFL_GAME, networks: ["CBS", "FOX"] });
  expect(text.startsWith("NFL · ")).toBe(true);
  expect(text.endsWith(" · CBS, FOX")).toBe(true);
});

test("no networks, no trailing separator", () => {
  expect(whenAndWhere({ ...NFL_GAME, networks: [] }).endsWith(" · ")).toBe(false);
});
