/** "Sync with my TV", the switch for keeping in sync automatically, and what
 * the last sync came to: the delay it set, or, when the listener's TV is
 * ahead of the commentator's, how long to pause the TV. */

import { Pressable, StyleSheet, Switch, Text, View } from "react-native";

import { Notice } from "@/components/Notice";
import type { TvSyncState } from "@/hooks/useTvSync";
import { AUTO_LISTEN_SECONDS, MISSES_BEFORE_NOTICE } from "@/lib/autoSync";
import { formatSeconds } from "@/lib/delay";
import { RECORDING_SECONDS } from "@/lib/tvSync";
import { COLOR, DIMMED, FONT, MIN_TOUCH, RADIUS, SPACE } from "@/theme";

interface SyncPanelProps {
  state: TvSyncState;
  onSync(): void;
  autoSync: boolean;
  onAutoSyncChange(on: boolean): void;
}

export function SyncPanel({ state, onSync, autoSync, onAutoSyncChange }: SyncPanelProps) {
  const isBusy = state.kind === "recording" || state.kind === "matching";
  const outcome = describe(state);
  return (
    <View style={styles.panel}>
      <Pressable accessibilityRole="button" disabled={isBusy} onPress={onSync} style={[styles.button, isBusy && styles.busy]}>
        <Text style={styles.label}>Sync with my TV</Text>
      </Pressable>
      <View style={styles.auto}>
        <Text style={styles.autoLabel}>Keep in sync automatically</Text>
        <Switch accessibilityLabel="Keep in sync automatically" value={autoSync} onValueChange={onAutoSyncChange} />
      </View>
      {outcome ? <Notice text={outcome.text} isError={outcome.isError} /> : null}
    </View>
  );
}

function describe(state: TvSyncState): { text: string; isError?: boolean } | null {
  switch (state.kind) {
    case "idle":
      return { text: "Turn the TV up a little and hold the phone near it." };
    case "recording":
      return state.auto
        ? { text: `Checking your TV is still in sync (the commentary goes quiet for ${AUTO_LISTEN_SECONDS} s)…` }
        : { text: `Listening to your TV for ${RECORDING_SECONDS} seconds…` };
    case "matching":
      return { text: "Matching it to the commentator's TV…" };
    case "synced":
      return describeSynced(state);
    case "not-found":
      return describeNotFound(state);
    case "failed":
      return { text: state.detail, isError: !state.auto };
  }
}

function describeSynced(state: Extract<TvSyncState, { kind: "synced" }>): { text: string } {
  if (state.pauseTv > 0) {
    return { text: `Your TV is ahead of the commentator's. Pause your TV for ${formatSeconds(state.pauseTv)}, then play.` };
  }
  if (state.auto && !state.changed) return { text: "Checked: still in sync." };
  if (state.auto) return { text: `Your TV's timing changed: the commentary now runs ${formatSeconds(state.delay)} behind.` };
  return { text: `Synced: the commentary now runs ${formatSeconds(state.delay)} behind.` };
}

function describeNotFound(state: Extract<TvSyncState, { kind: "not-found" }>): { text: string; isError?: boolean } | null {
  if (!state.auto) {
    return {
      text: "Couldn't find your TV's sound in the commentator's. Make sure it's the same game and channel, or set the delay by hand.",
      isError: true,
    };
  }
  // An automatic check that misses now and then says nothing; repeated misses do.
  if (state.misses < MISSES_BEFORE_NOTICE) return null;
  return { text: "Auto-sync can't hear your TV. Turn it up, or sync by hand.", isError: true };
}

const styles = StyleSheet.create({
  panel: { gap: SPACE.sm, paddingVertical: SPACE.md },
  button: {
    minHeight: MIN_TOUCH,
    justifyContent: "center",
    alignItems: "center",
    borderRadius: RADIUS,
    backgroundColor: COLOR.accent,
  },
  busy: { opacity: DIMMED },
  label: { color: COLOR.text, fontSize: FONT.body, fontWeight: "700" },
  auto: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: MIN_TOUCH },
  autoLabel: { color: COLOR.text, fontSize: FONT.body },
});
