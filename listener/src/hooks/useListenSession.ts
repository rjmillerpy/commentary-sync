/** Everything one listening screen runs: the playlist, delayed playback,
 * check-ins, syncing with the TV (on opening, by hand and automatically),
 * the listener's own pause, fine-tune and volume, the phone's connection,
 * and the one sync status all of that adds up to (lib/syncStatus.ts).
 * Listening ends when the commentator ends the stream. */

import type { Stream } from "@commentary-sync/client/schema";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Linking } from "react-native";

import { useAutoSync } from "@/hooks/useAutoSync";
import { useConnectivity } from "@/hooks/useConnectivity";
import { useDelayedPlayback } from "@/hooks/useDelayedPlayback";
import { useForeground } from "@/hooks/useForeground";
import { useListening } from "@/hooks/useListening";
import { usePlaylist } from "@/hooks/usePlaylist";
import { useStoredNumber } from "@/hooks/useStoredNumber";
import { useStreamEnded } from "@/hooks/useStreamEnded";
import { type SyncOptions, useTvSync } from "@/hooks/useTvSync";
import { clampDelay, clampFineTune, DEFAULT_DELAY_SECONDS } from "@/lib/delay";
import { PREFERENCE_KEYS } from "@/lib/preferences";
import { type SyncAction, syncStatus } from "@/lib/syncStatus";
import type { DelayPlan } from "@/lib/tvSync";
import { clampVolume, DEFAULT_VOLUME } from "@/lib/volume";

export function useListenSession(stream: Stream) {
  const choices = useListenerChoices();
  const { baseDelay, setBaseDelay, fineTune, isSyncOn, isPaused } = choices;
  const [hasSynced, setHasSynced] = useState(false);
  const hasEnded = useStreamEnded(stream.id);
  const playlist = usePlaylist(stream.id);
  const connectivity = useConnectivity();
  const foregroundedAt = useForeground();

  const onPlan = useCallback(
    (plan: DelayPlan) => {
      setBaseDelay(plan.delay);
      setHasSynced(true);
    },
    [setBaseDelay],
  );
  const delay = clampDelay(baseDelay + fineTune);
  const sync = useTvSync(stream.id, onPlan, baseDelay);
  const isListening = sync.state.kind === "recording";
  const isAutoCheck = sync.state.kind === "recording" && sync.state.auto;

  // While the phone listens, the commentary can't play aloud or it would hear
  // itself: a requested sync pauses it, an automatic check only mutes it.
  const url = playlist.kind === "ready" && !hasEnded ? playlist.url : null;
  const playback = useDelayedPlayback(url, delay, {
    isSuspended: isListening && !isAutoCheck,
    isMuted: isAutoCheck || choices.isMuted,
    isPausedByListener: isPaused,
    volume: choices.volume,
    jumpAt: choices.jumpAt,
    reconnectedAt: connectivity.reconnectedAt,
  });
  const isPlaying = playback.phase !== "loading" && playback.phase !== "reconnecting" && playback.phase !== "paused";
  useListening(stream.id, isPlaying);

  const { start } = sync;
  useSyncOnOpening(isSyncOn, start);
  const check = useCallback(() => void start({ auto: true }), [start]);
  useAutoSync({
    // Never behind the listener's back: not while they've paused or turned it off.
    enabled: isSyncOn && hasSynced && isPlaying && connectivity.isConnected,
    isBusy: isListening || sync.state.kind === "matching",
    triggers: [connectivity.reconnectedAt, foregroundedAt, playback.recoveredAt],
    check,
  });

  const status = syncStatus({
    tv: sync.state,
    phase: playback.phase,
    pausedBehind: Math.max(0, (playback.behind ?? delay) - delay),
    hasSynced,
    isSyncOn,
    isOnline: connectivity.isConnected,
  });
  const actions = useActions({ start, ...choices });
  return { ...choices, ...actions, hasEnded, playlist, status, delay, behind: playback.behind };
}

/** What the listener chose: remembered (fine-tune, volume) or for this listen. */
function useListenerChoices() {
  const [baseDelay, setRawBaseDelay] = useState(DEFAULT_DELAY_SECONDS);
  const [fineTune, setFineTune] = useStoredNumber(PREFERENCE_KEYS.fineTune, 0, clampFineTune);
  const [volume, setVolume] = useStoredNumber(PREFERENCE_KEYS.volume, DEFAULT_VOLUME, clampVolume);
  const [isMuted, setIsMuted] = useState(false);
  const [isSyncOn, setIsSyncOn] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [jumpAt, setJumpAt] = useState(0);
  const setBaseDelay = useCallback((seconds: number) => setRawBaseDelay(clampDelay(seconds)), []);
  return { baseDelay, setBaseDelay, fineTune, setFineTune, volume, setVolume, isMuted, setIsMuted, isSyncOn, setIsSyncOn, isPaused, setIsPaused, jumpAt, setJumpAt };
}

/** Opening a commentator syncs with the TV straight away (UI rule 0.2:
 * sync is invisible until it breaks): no button to find first. */
function useSyncOnOpening(isSyncOn: boolean, start: StartSync): void {
  const hasStarted = useRef(false);
  useEffect(() => {
    if (hasStarted.current || !isSyncOn) return;
    hasStarted.current = true;
    void start();
  }, [isSyncOn, start]);
}

type StartSync = (options?: SyncOptions) => Promise<unknown>;

interface ActionInputs {
  start: StartSync;
  isPaused: boolean;
  setIsSyncOn(on: boolean): void;
  setIsPaused(paused: boolean): void;
  setJumpAt(at: number): void;
}

/** What tapping the status does, and pausing: one tap each, no confirmations. */
function useActions({ start, isPaused, setIsSyncOn, setIsPaused, setJumpAt }: ActionInputs) {
  const jumpBack = useCallback(() => {
    setIsPaused(false);
    setJumpAt(Date.now());
  }, [setIsPaused, setJumpAt]);

  const act = useCallback(
    (action: SyncAction) => {
      if (action === "jump") return jumpBack();
      if (action === "settings") return void Linking.openSettings();
      if (action === "turn-on") setIsSyncOn(true);
      setJumpAt(Date.now()); // a resync may seek at once, cool-down or not
      void start();
    },
    [jumpBack, setIsSyncOn, setJumpAt, start],
  );

  const togglePause = useCallback(() => (isPaused ? jumpBack() : setIsPaused(true)), [isPaused, jumpBack, setIsPaused]);

  return useMemo(() => ({ act, togglePause }), [act, togglePause]);
}
