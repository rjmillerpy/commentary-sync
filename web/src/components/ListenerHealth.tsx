/** Who is listening and how their sync is going (UI rule 12): how many
 * listen, how many matched their TV to the commentator's, how late they hear
 * them, and why the rest didn't match. */

import type { SyncHealth } from "@commentary-sync/client/schema";

interface Props {
  listeners: number | null;
  health: SyncHealth | null;
}

const UNKNOWN = "…";

export default function ListenerHealth({ listeners, health }: Props) {
  const tried = health === null ? 0 : health.in_sync + health.not_heard;
  return (
    <section aria-label="Your listeners" aria-live="polite">
      <dl className="stats">
        <div>
          <dt>Listening</dt>
          <dd>{listeners ?? UNKNOWN}</dd>
        </div>
        <div>
          <dt>In sync with their TV</dt>
          <dd>{health === null ? UNKNOWN : tried === 0 ? "No one yet" : `${health.in_sync} of ${tried}`}</dd>
        </div>
        <div>
          <dt>They hear you</dt>
          <dd>{lateness(health)}</dd>
        </div>
      </dl>
      {health !== null && health.not_heard > 0 && <p className="hint">{notHeard(health.not_heard)}</p>}
    </section>
  );
}

function lateness(health: SyncHealth | null): string {
  if (health === null || health.typical_delay_seconds === null) return UNKNOWN;
  return `about ${Math.round(health.typical_delay_seconds)} s late`;
}

function notHeard(count: number): string {
  const who = count === 1 ? "1 listener's TV doesn't" : `${count} listeners' TVs don't`;
  return `${who} sound like yours: they may be on another channel or a different broadcast of the game, or have the TV too quiet. They can still set their delay by hand.`;
}
