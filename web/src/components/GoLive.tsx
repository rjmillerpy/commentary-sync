/** The last setup step: go live, once a game is picked and the mic is open,
 * saying what's still missing until then. */

import type { BroadcastPhase } from "@/hooks/useBroadcast";

interface Props {
  phase: BroadcastPhase;
  missing: string | null;
  error: string | null;
  onStart: () => void;
}

export default function GoLive({ phase, missing, error, onStart }: Props) {
  const isStarting = phase === "starting";
  return (
    <section className="card" aria-labelledby="go-live-title">
      <h2 id="go-live-title">3. Go live</h2>
      {error !== null && <p role="alert">{error}</p>}
      <p className="hint" role="status">
        {isStarting ? "Going live…" : (missing ?? "Ready. Listeners can find you as soon as you go live.")}
      </p>
      <button type="button" disabled={missing !== null || isStarting} onClick={onStart}>
        Go live
      </button>
    </section>
  );
}
