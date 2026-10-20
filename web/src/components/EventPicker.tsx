"use client";

/** The games a commentator can go live on: scheduled or in progress. */

import { useEffect, useState } from "react";

import EventOption from "@/components/EventOption";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { SportsEvent } from "@commentary-sync/client/schema";

const OPEN_STATUSES: ReadonlySet<string> = new Set(["scheduled", "live"]);

type Games = { state: "loading" } | { state: "ready"; events: SportsEvent[] } | { state: "failed"; detail: string };

interface Props {
  chosenId: string | null;
  isLocked: boolean;
  onChoose: (eventId: string) => void;
}

export default function EventPicker({ chosenId, isLocked, onChoose }: Props) {
  const [games, setGames] = useState<Games>({ state: "loading" });

  useEffect(() => {
    let isCurrent = true;
    api
      .upcomingEvents()
      .then((page) => {
        const events = page.items.filter((event) => OPEN_STATUSES.has(event.status));
        if (isCurrent) setGames({ state: "ready", events });
      })
      .catch((failure: unknown) => {
        const detail = failure instanceof ApiError ? failure.detail : "Couldn't load games.";
        if (isCurrent) setGames({ state: "failed", detail });
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  return (
    <section className="card" aria-labelledby="games-title">
      <h2 id="games-title">1. Pick a game</h2>
      {games.state === "loading" && <p>Loading games…</p>}
      {games.state === "failed" && <p role="alert">{games.detail}</p>}
      {games.state === "ready" && games.events.length === 0 && <p>No games on or coming up.</p>}
      {games.state === "ready" && games.events.length > 0 && (
        <ul className="options" role="radiogroup" aria-labelledby="games-title">
          {games.events.map((event) => (
            <EventOption
              key={event.id}
              event={event}
              isChosen={event.id === chosenId}
              isDisabled={isLocked}
              onChoose={onChoose}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
