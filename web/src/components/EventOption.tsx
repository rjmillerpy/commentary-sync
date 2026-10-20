"use client";

/** One game in the picker. Memoized: the list re-renders on every choice (rule 68). */

import { memo } from "react";

import type { SportsEvent } from "@commentary-sync/client/schema";

const START_FORMAT: Intl.DateTimeFormatOptions = { weekday: "short", hour: "numeric", minute: "2-digit" };

interface Props {
  event: SportsEvent;
  isChosen: boolean;
  isDisabled: boolean;
  onChoose: (eventId: string) => void;
}

function EventOption({ event, isChosen, isDisabled, onChoose }: Props) {
  const starts = new Date(event.starts_at).toLocaleString(undefined, START_FORMAT);
  const networks = event.networks.length > 0 ? ` · ${event.networks.join(", ")}` : "";
  return (
    <li>
      <label className={isChosen ? "option chosen" : "option"}>
        <input
          type="radio"
          name="event"
          value={event.id}
          checked={isChosen}
          disabled={isDisabled}
          onChange={() => onChoose(event.id)}
        />
        <span className="option-title">{event.title}</span>
        <span className="option-detail">
          {event.league.toUpperCase()} · {event.status === "live" ? "Live now" : starts}
          {networks}
        </span>
      </label>
    </li>
  );
}

export default memo(EventOption);
