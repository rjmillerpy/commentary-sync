/** Everything one listening screen runs: the playlist, delayed playback,
 * check-ins, syncing with the TV by hand and automatically, and the phone's
 * connection. Listening ends when the commentator ends the stream. */

import type { Stream } from "@commentary-sync/client/schema";
import { useCallback, useState } from "react";

import { useAutoSync } from "@/hooks/useAutoSync";
import { useConnectivity } from "@/hooks/useConnectivity";
import { useDelayedPlayback } from "@/hooks/useDelayedPlayback";
import { useForeground } from "@/hooks/useForeground";
import { useListening } from "@/hooks/useListening";
import { usePlaylist } from "@/hooks/usePlaylist";
import { useStreamEnded } from "@/hooks/useStreamEnded";
import { useTvSync } from "@/hooks/useTvSync";
import { DEFAULT_DELAY_SECONDS } from "@/lib/delay";
import type { DelayPlan } from "@/lib/tvSync";

export function useListenSession(stream: Stream) {
  const [delay, setDelay] = useState(DEFAULT_DELAY_SECONDS);
  const [hasSynced, setHasSynced] = useState(false);
  const [autoSync, setAutoSync] = useState(true);
  const hasEnded = useStreamEnded(stream.id);
  const playlist = usePlaylist(stream.id);
  const connectivity = useConnectivity();
  const foregroundedAt = useForeground();

  const onPlan = useCallback((plan: DelayPlan) => {
    setDelay(plan.delay);
    setHasSynced(true);
  }, []);
  const sync = useTvSync(stream.id, onPlan, delay);
  const isListening = sync.state.kind === "recording";
  const isAutoCheck = sync.state.kind === "recording" && sync.state.auto;

  // While the phone listens, the commentary can't play aloud or it would hear
  // itself: a requested sync pauses it, an automatic check only mutes it.
  const url = playlist.kind === "ready" && !hasEnded ? playlist.url : null;
  const playback = useDelayedPlayback(url, delay, {
    isSuspended: isListening && !isAutoCheck,
    isMuted: isAutoCheck,
    reconnectedAt: connectivity.reconnectedAt,
  });
  const isPlaying = playback.phase === "playing" || playback.phase === "holding";
  useListening(stream.id, isPlaying);

  const { start } = sync;
  const check = useCallback(() => void start({ auto: true }), [start]);
  useAutoSync({
    enabled: autoSync && hasSynced && isPlaying && connectivity.isConnected,
    isBusy: isListening || sync.state.kind === "matching",
    triggers: [connectivity.reconnectedAt, foregroundedAt, playback.recoveredAt],
    check,
  });

  return { delay, setDelay, hasEnded, playlist, playback, sync, autoSync, setAutoSync, isOnline: connectivity.isConnected };
}
