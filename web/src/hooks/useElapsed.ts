/** How long the stream has been live, as a clock reads: "4:05", "1:02:03",
 * ticking every second. */

import { useEffect, useState } from "react";

const SECOND_MS = 1_000;
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3_600;

export function useElapsed(startedAt: string | null): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const timer = setInterval(() => setNow(Date.now()), SECOND_MS);
    return () => clearInterval(timer);
  }, [startedAt]);
  if (startedAt === null) return null;
  return formatElapsed(Math.max(0, Math.floor((now - Date.parse(startedAt)) / SECOND_MS)));
}

export function formatElapsed(seconds: number): string {
  const hours = Math.floor(seconds / SECONDS_PER_HOUR);
  const minutes = Math.floor((seconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const rest = String(seconds % SECONDS_PER_MINUTE).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}
