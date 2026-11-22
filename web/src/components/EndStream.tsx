"use client";

/** Ending the stream: the one action that cuts every listener off, so it
 * asks once, in place, never in a dialog (UI rule 5.3). */

import { useState } from "react";

interface Props {
  listeners: number | null;
  onEnd: () => void;
}

export default function EndStream({ listeners, onEnd }: Props) {
  const [isAsking, setIsAsking] = useState(false);
  if (!isAsking) {
    return (
      <button type="button" className="secondary" onClick={() => setIsAsking(true)}>
        End stream
      </button>
    );
  }
  const who = listeners === null || listeners === 0 ? "the stream" : `the stream for ${listeners === 1 ? "1 listener" : `${listeners} listeners`}`;
  return (
    <div className="confirm" role="group" aria-label="End the stream?">
      <p className="status">End {who}?</p>
      <button type="button" className="danger" onClick={onEnd}>
        Yes, end it
      </button>
      <button type="button" className="secondary" onClick={() => setIsAsking(false)}>
        Keep going
      </button>
    </div>
  );
}
