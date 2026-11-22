/** Plays a stream's HLS playlist and keeps it `delay` seconds behind real
 * time (lib/delay.ts), checking twice a second. Keeps playing with the
 * screen off: the listener is watching the TV, not the phone.
 *
 * - `isSuspended`: paused (the phone is listening to the TV for a sync).
 * - `isMuted`: playing but silent (an automatic re-check is listening), so
 *   the commentary's place in time doesn't move.
 * - `isPausedByListener`: the listener paused it. Nothing corrects it while
 *   paused, and `behind` keeps growing; un-pausing jumps straight back.
 * - `jumpAt`: a newer time clears the seek cool-down, so the next tick may
 *   seek at once (after a sync, a resync or un-pausing: things the listener
 *   asked for, where waiting would look broken).
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
import { correction, type Correction, nextHistory, NO_SEEKS, type SeekHistory } from "@/lib/delay";

export const TICK_MS = 500;

export type PlaybackPhase = "loading" | "playing" | "drifting" | "holding" | "stuck" | "reconnecting" | "paused";

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
  isPausedByListener?: boolean;
  /** 0 to 1. */
  volume?: number;
  jumpAt?: number;
  reconnectedAt?: number | null;
}

interface TickState {
  isHolding: boolean;
  history: SeekHistory;
}

export function useDelayedPlayback(url: string | null, delay: number, options: PlaybackOptions = {}): Playback {
  const { isSuspended = false, isMuted = false, isPausedByListener = false, volume = 1, jumpAt = 0, reconnectedAt = null } = options;
  const player = useVideoPlayer(url, (created) => {
    created.staysActiveInBackground = true;
    created.showNowPlayingNotification = true;
    created.preservesPitch = true; // a 5% speed change shouldn't change voices
    created.play();
  });
  // The latest delay, read by the running tick without restarting it.
  const delayRef = useRef(delay);
  useEffect(() => {
    delayRef.current = delay;
  }, [delay]);
  const state = useRef<TickState>({ isHolding: false, history: NO_SEEKS });
  useEffect(() => {
    state.current.history = NO_SEEKS;
  }, [jumpAt]);
  const [playback, setPlayback] = useState<Playback>({ phase: "loading", behind: null, recoveredAt: null });
  const recovery = useRecovery(player, url, reconnectedAt);
  const isStopped = isSuspended || isPausedByListener;
  useDelayChange(player, delay, url !== null && !isStopped);

  useEffect(() => {
    if (url === null || isStopped) return;
    player.play(); // from a pause or suspension; a no-op otherwise
    const timer = setInterval(() => {
      if (player.status === "error") {
        recovery.current.failed();
        setPlayback((previous) => ({ ...previous, phase: "reconnecting", behind: null }));
        return;
      }
      const next = tick(player, delayRef.current, state.current);
      recovery.current.healthy();
      setPlayback((previous) => afterTick(previous, next));
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [player, url, isStopped, recovery]);

  usePause(player, isSuspended, isPausedByListener, setPlayback);
  useEffect(() => sound(player, isMuted, volume), [player, isMuted, volume]);
  return playback;
}

/** A changed delay (a sync, a fine-tune) is applied at once, by seeking the
 * difference: the listener hears a fine-tune as they tap it (UI rule 1.4). */
function useDelayChange(player: VideoPlayer, delay: number, isRunning: boolean): void {
  const previous = useRef(delay);
  useEffect(() => {
    const change = delay - previous.current;
    previous.current = delay;
    if (change === 0 || !isRunning || player.currentOffsetFromLive === null) return;
    player.seekBy(-change);
  }, [player, delay, isRunning]);
}

/** Paused by the listener: say so, and keep `behind` growing as live moves on. */
function usePause(
  player: VideoPlayer,
  isSuspended: boolean,
  isPausedByListener: boolean,
  setPlayback: (update: (previous: Playback) => Playback) => void,
): void {
  useEffect(() => {
    if (!isSuspended && !isPausedByListener) return;
    stop(player);
    if (!isPausedByListener) return;
    const read = () => setPlayback((previous) => ({ ...previous, phase: "paused", behind: player.currentOffsetFromLive }));
    read();
    const timer = setInterval(read, TICK_MS);
    return () => clearInterval(timer);
  }, [player, isSuspended, isPausedByListener, setPlayback]);
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

function stop(player: VideoPlayer): void {
  player.pause();
  player.playbackRate = 1;
}

function sound(player: VideoPlayer, isMuted: boolean, volume: number): void {
  player.muted = isMuted;
  player.volume = volume;
}

/** A reloaded player loads again before it plays: until it plays, it is
 * still reconnecting, and the moment it plays is when it recovered. */
function afterTick(previous: Playback, next: Omit<Playback, "recoveredAt">): Playback {
  if (previous.phase !== "reconnecting") return { ...next, recoveredAt: previous.recoveredAt };
  if (next.phase === "loading") return previous;
  return { ...next, recoveredAt: Date.now() };
}

function tick(player: VideoPlayer, delay: number, state: TickState): Omit<Playback, "recoveredAt"> {
  const now = Date.now();
  const reading = { offset: player.currentOffsetFromLive, position: player.currentTime, isHolding: state.isHolding };
  const step = correction(reading, delay, state.history, now);
  apply(player, step, state);
  state.history = nextHistory(state.history, step, now);
  if (reading.offset === null) return { phase: "loading", behind: null };
  return { phase: phaseOf(step, state.isHolding), behind: reading.offset };
}

function apply(player: VideoPlayer, step: Correction, state: TickState): void {
  player.playbackRate = step.kind === "rate" ? step.rate : 1;
  if (step.kind === "seek") player.seekBy(step.by);
  if (step.kind === "hold") {
    player.pause();
    state.isHolding = true;
  }
  if (step.kind === "resume") {
    player.play();
    state.isHolding = false;
  }
}

function phaseOf(step: Correction, isHolding: boolean): PlaybackPhase {
  if (isHolding) return "holding";
  if (step.kind === "stuck") return "stuck";
  return step.kind === "none" || step.kind === "resume" ? "playing" : "drifting";
}
