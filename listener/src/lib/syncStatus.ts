/** The one sync status the listener sees (UI rule 1.1): which of seven
 * states the commentary is in against their TV, the words for it, and what
 * tapping it does. Everything the listening screen knows goes in; exactly
 * one status comes out, so no two messages ever disagree.
 *
 * Order matters: the listener's own pause beats everything (their choice
 * stays until they change it), then the connection, then syncing being off,
 * then what the last TV check said, then how playback is holding the delay. */

import type { PlaybackPhase } from "@/hooks/useDelayedPlayback";
import type { TvSyncState } from "@/hooks/useTvSync";
import { AUTO_LISTEN_SECONDS, MISSES_BEFORE_NOTICE } from "@/lib/autoSync";
import { formatBehind, formatSeconds } from "@/lib/delay";
import { RECORDING_SECONDS } from "@/lib/tvSync";

export type SyncStatusKind = "synced" | "syncing" | "drifting" | "desynced" | "paused" | "unavailable" | "off";

/** What tapping the status does; null: nothing to do but wait. */
export type SyncAction = "sync" | "jump" | "turn-on" | "settings";

export interface SyncStatus {
  kind: SyncStatusKind;
  label: string;
  detail: string | null;
  action: SyncAction | null;
}

export interface SyncInputs {
  tv: TvSyncState;
  phase: PlaybackPhase;
  /** While paused by the listener: how far behind their TV the commentary now is. */
  pausedBehind: number;
  hasSynced: boolean;
  isSyncOn: boolean;
  isOnline: boolean;
}

/** Said out loud at once by screen readers; the rest wait their turn. */
export const URGENT_KINDS: ReadonlySet<SyncStatusKind> = new Set(["desynced", "unavailable"]);

const status = (kind: SyncStatusKind, label: string, detail: string | null = null, action: SyncAction | null = null): SyncStatus => ({
  kind,
  label,
  detail,
  action,
});

const OUT_OF_SYNC = "Out of sync · Tap to resync";
const CANT_HEAR = "Can't hear your TV";

export function syncStatus(inputs: SyncInputs): SyncStatus {
  if (inputs.phase === "paused") return status("paused", `You're ${formatBehind(inputs.pausedBehind)} behind · Jump back in`, null, "jump");
  if (!inputs.isOnline || inputs.phase === "reconnecting") {
    return status("syncing", "Reconnecting…", "No connection. The commentary comes back at the same delay.");
  }
  if (!inputs.isSyncOn) return status("off", "Sync off", "You're setting the delay yourself. Tap to sync with your TV.", "turn-on");
  return fromTv(inputs.tv) ?? fromPlayback(inputs.phase, inputs.hasSynced);
}

function fromTv(tv: TvSyncState): SyncStatus | null {
  switch (tv.kind) {
    case "recording":
      return tv.auto
        ? status("syncing", "Checking your TV…", `The commentary goes quiet for ${AUTO_LISTEN_SECONDS} seconds.`)
        : status("syncing", "Listening to your TV…", `Hold the phone near the TV for ${RECORDING_SECONDS} seconds.`);
    case "matching":
      return status("syncing", "Lining up with your TV…");
    case "synced":
      if (tv.pauseTv === 0) return null;
      return status("drifting", `Pause your TV for ${formatSeconds(tv.pauseTv)}`, "Your TV is ahead of the commentator's. Then play it and tap here.", "sync");
    case "not-found":
      return fromNotFound(tv);
    case "failed":
      if (tv.reason === "microphone") return status("unavailable", CANT_HEAR, "Allow the microphone in Settings, then tap here.", "settings");
      return tv.auto ? null : status("desynced", OUT_OF_SYNC, tv.detail, "sync");
    case "idle":
      return null;
  }
}

function fromNotFound(tv: Extract<TvSyncState, { kind: "not-found" }>): SyncStatus | null {
  // An automatic check that misses now and then says nothing; repeated misses do.
  if (tv.auto && tv.misses < MISSES_BEFORE_NOTICE) return null;
  const detail = "Couldn't match your TV's sound to the commentator's. Same game and channel? Turn the TV up, hold the phone near it, and tap here.";
  return tv.auto ? status("unavailable", CANT_HEAR, detail, "sync") : status("desynced", OUT_OF_SYNC, detail, "sync");
}

function fromPlayback(phase: PlaybackPhase, hasSynced: boolean): SyncStatus {
  switch (phase) {
    case "loading":
      return status("syncing", "Starting the commentary…");
    case "holding":
      return status("syncing", "Lining up the commentary…");
    case "stuck":
      return status("desynced", OUT_OF_SYNC, "The commentary couldn't catch up with your TV.", "sync");
    default:
      break;
  }
  if (!hasSynced) return status("desynced", "Not synced yet · Tap to sync", "Hold the phone near your TV.", "sync");
  return phase === "drifting" ? status("drifting", "Catching up", "Adjusting the commentary to your TV.") : status("synced", "Synced with your TV");
}
