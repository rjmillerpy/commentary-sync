/** Plays a stream's HLS playlist and keeps it `delay` seconds behind real
 * time (lib/delay.ts), checking twice a second. Keeps playing with the
 * screen off: the listener is watching the TV, not the phone.
 *
 * - `isSuspended`: paused (the phone is listening to the TV for a sync).
 * - `isMuted`: playing but silent (an automatic re-check is listening), so
 *   the commentary's place in time doesn't move.
 * - A player that fails (the connection dropped, the server blinked) is
 *   reloaded by itself, with growing waits, and at once when the phone's
 *   connection comes back (`reconnectedAt`). The delay control then puts the
 *   commentary back at the same delay: every segment carries its recording
 *   time. `recoveredAt` says when it last came back, so the app can also
 *   re-check the TV, which may have stalled on the same Wi-Fi.
 */

import { useVideoPlayer, type VideoPlayer } from "expo-video";
import { useCallback, useEffect, useRef, useState } from "react";

import { backoffMs } from "@/lib/autoSync";
import { correction } from "@/lib/delay";

export const TICK_MS = 500;

export type PlaybackPhase = "loading" | "playing" | "holding" | "reconnecting";

export interface Playback {
  phase: PlaybackPhase;
  /** Seconds behind real time, once the player knows. */
  behind: number | null;
  /** When playback last came back after failing (ms since the epoch), or null. */
  recoveredAt: number | null;
}

export interface PlaybackOptions {
  isSuspended?: boolean;
  isMuted?: boolean;
  reconnectedAt?: number | null;
}

export function useDelayedPlayback(
  url: string | null,
  delay: number,
  { isSuspended = false, isMuted = false, reconnectedAt = null }: PlaybackOptions = {},
): Playback {
  const player = useVideoPlayer(url, (created) => {
    created.staysActiveInBackground = true;
    created.showNowPlayingNotification = true;
    created.play();
  });
  // The latest delay, read by the running tick without restarting it.
  const delayRef = useRef(delay);
  useEffect(() => {
    delayRef.current = delay;
  }, [delay]);
  const [playback, setPlayback] = useState<Playback>({ phase: "loading", behind: null, recoveredAt: null });
  const recovery = useRecovery(player, url, reconnectedAt);

  useEffect(() => {
    if (url === null || isSuspended) return;
    const holding = { current: false };
    player.play(); // from a suspension; a no-op otherwise
    const timer = setInterval(() => {
      if (player.status === "error") {
        recovery.current.failed();
        setPlayback((previous) => ({ ...previous, phase: "reconnecting", behind: null }));
        return;
      }
      const next = tick(player, delayRef.current, holding);
      recovery.current.healthy();
      setPlayback((previous) => afterTick(previous, next));
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [player, url, isSuspended, recovery]);

  useEffect(() => {
    if (isSuspended) player.pause();
  }, [player, isSuspended]);

  useEffect(() => mute(player, isMuted), [player, isMuted]);

  return playback;
}

/** Reloads a failed player: after 1, 2, 4 ... 30 s, or at once on reconnect. */
function useRecovery(player: VideoPlayer, url: string | null, reconnectedAt: number | null) {
  const attempts = useRef(0);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reload = useCallback(() => {
    pending.current = null;
    if (url === null) return;
    attempts.current += 1;
    void player.replaceAsync(url).then(
      () => player.play(),
      () => undefined, // still failing: the next tick schedules another try
    );
  }, [player, url]);

  const failed = useCallback(() => {
    if (pending.current === null) pending.current = setTimeout(reload, backoffMs(attempts.current));
  }, [reload]);
  const healthy = useCallback(() => {
    attempts.current = 0;
  }, []);

  useEffect(() => {
    if (reconnectedAt === null || player.status !== "error") return;
    if (pending.current !== null) clearTimeout(pending.current);
    reload();
  }, [player, reconnectedAt, reload]);

  useEffect(
    () => () => {
      if (pending.current !== null) clearTimeout(pending.current);
    },
    [],
  );

  // Read through a ref by the running tick, so it isn't restarted.
  const handlers = useRef({ failed, healthy });
  useEffect(() => {
    handlers.current = { failed, healthy };
  }, [failed, healthy]);
  return handlers;
}

function mute(player: VideoPlayer, isMuted: boolean): void {
  player.muted = isMuted;
}

/** A reloaded player loads again before it plays: until it plays, it is
 * still reconnecting, and the moment it plays is when it recovered. */
function afterTick(previous: Playback, next: Omit<Playback, "recoveredAt">): Playback {
  if (previous.phase !== "reconnecting") return { ...next, recoveredAt: previous.recoveredAt };
  if (next.phase === "loading") return previous;
  return { ...next, recoveredAt: Date.now() };
}

function tick(player: VideoPlayer, delay: number, holding: { current: boolean }): Omit<Playback, "recoveredAt"> {
  const reading = { offset: player.currentOffsetFromLive, position: player.currentTime, isHolding: holding.current };
  const step = correction(reading, delay);
  if (step.kind === "seek") player.seekBy(step.by);
  if (step.kind === "hold") {
    player.pause();
    holding.current = true;
  }
  if (step.kind === "resume") {
    player.play();
    holding.current = false;
  }
  if (reading.offset === null) return { phase: "loading", behind: null };
  return { phase: holding.current ? "holding" : "playing", behind: reading.offset };
}
