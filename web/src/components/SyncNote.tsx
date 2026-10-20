/** Whether listeners can sync their TVs to this commentator's, and what
 * keeps it working. */

import type { ReferenceStatus } from "@/hooks/useReference";

const NOTES: Record<Exclude<ReferenceStatus, "off">, string> = {
  on: "Listeners can sync their TVs to yours. Keep your TV's sound on its speakers, where your mic can hear it, not in headphones.",
  unavailable: "TV sync is off: this browser wouldn't open your microphone a second time. Listeners can still set their delay by hand.",
};

export default function SyncNote({ status }: { status: ReferenceStatus }) {
  if (status === "off") return null;
  return (
    <p className="hint" role="status">
      {NOTES[status]}
    </p>
  );
}
