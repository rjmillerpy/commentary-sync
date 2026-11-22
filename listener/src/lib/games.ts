/** The game list (UI rule 7.1): browsing starts from what's on TV.
 * Games someone is commentating come first, with how many are; then every
 * other game on now or coming up. */

import type { SportsEvent, Stream } from "@commentary-sync/client/schema";

export interface GameEntry {
  game: SportsEvent;
  commentators: number;
}

export interface GameSections {
  withCommentary: GameEntry[];
  others: GameEntry[];
}

const OPEN = new Set<SportsEvent["status"]>(["live", "scheduled"]);
const START_FORMAT: Intl.DateTimeFormatOptions = { weekday: "short", hour: "numeric", minute: "2-digit" };

export function sectionGames(games: readonly SportsEvent[], live: readonly Stream[]): GameSections {
  const counts = new Map<string, number>();
  for (const stream of live) counts.set(stream.event_id, (counts.get(stream.event_id) ?? 0) + 1);
  const entries = games.filter((game) => OPEN.has(game.status)).map((game) => ({ game, commentators: counts.get(game.id) ?? 0 }));
  return {
    withCommentary: entries.filter((entry) => entry.commentators > 0).sort((a, b) => b.commentators - a.commentators),
    others: entries.filter((entry) => entry.commentators === 0),
  };
}

export function commentatorCount(count: number): string {
  if (count === 0) return "No commentary yet";
  return count === 1 ? "1 commentator live" : `${count} commentators live`;
}

/** "NFL · Sun 1:00 PM · CBS, FOX". */
export function whenAndWhere(game: SportsEvent): string {
  const when = new Date(game.starts_at).toLocaleString([], START_FORMAT);
  return [game.league.toUpperCase(), when, game.networks.join(", ")].filter((part) => part.length > 0).join(" · ");
}
