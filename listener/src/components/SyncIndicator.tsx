/** The one sync status (UI rule 1.1, lib/syncStatus.ts): an icon, a
 * colour and words for each state, never colour alone. When there's
 * something to do, the status itself is the button. Screen readers hear
 * every change: politely, or at once when sync is broken (10). */

import { useEffect } from "react";
import { AccessibilityInfo, ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { useReduceMotion } from "@/hooks/useReduceMotion";
import { type SyncAction, type SyncStatus, type SyncStatusKind, URGENT_KINDS } from "@/lib/syncStatus";
import { COLOR, FONT, PRIMARY_TOUCH, RADIUS, SPACE, STATUS } from "@/theme";

const LOOK: Record<SyncStatusKind, { icon: string; color: string }> = {
  synced: { icon: "✓", color: STATUS.good },
  syncing: { icon: "↻", color: STATUS.working },
  drifting: { icon: "≈", color: STATUS.warning },
  desynced: { icon: "!", color: STATUS.error },
  paused: { icon: "‖", color: STATUS.neutral },
  unavailable: { icon: "×", color: STATUS.error },
  off: { icon: "–", color: STATUS.off },
};

const TIP = "This shows whether the commentary matches your TV. When it asks you to, tap it.";

interface SyncIndicatorProps {
  status: SyncStatus;
  onAct(action: SyncAction): void;
  showTip?: boolean;
}

export function SyncIndicator({ status, onAct, showTip = false }: SyncIndicatorProps) {
  const { kind, label, detail, action } = status;
  const { icon, color } = LOOK[kind];
  useAnnouncement(label, detail);
  return (
    <View style={styles.wrap}>
      <Pressable
        testID="sync-status"
        accessibilityRole={action === null ? "text" : "button"}
        accessibilityLabel={detail === null ? label : `${label}. ${detail}`}
        accessibilityLiveRegion={URGENT_KINDS.has(kind) ? "assertive" : "polite"}
        disabled={action === null}
        onPress={() => action !== null && onAct(action)}
        style={[styles.status, { borderColor: color }]}
      >
        <View style={styles.headline}>
          <Icon kind={kind} icon={icon} color={color} />
          <Text style={[styles.label, { color }]}>{label}</Text>
        </View>
        {detail === null ? null : <Text style={styles.detail}>{detail}</Text>}
      </Pressable>
      {showTip ? <Text style={styles.tip}>{TIP}</Text> : null}
    </View>
  );
}

function Icon({ kind, icon, color }: { kind: SyncStatusKind; icon: string; color: string }) {
  const isReduced = useReduceMotion();
  if (kind === "syncing" && !isReduced) return <ActivityIndicator color={color} accessibilityElementsHidden importantForAccessibility="no" />;
  return (
    <Text style={[styles.icon, { color }]} accessibilityElementsHidden importantForAccessibility="no">
      {icon}
    </Text>
  );
}

/** iOS has no live regions: it is told each change. Android's live region does it there. */
function useAnnouncement(label: string, detail: string | null): void {
  useEffect(() => {
    if (Platform.OS === "ios") AccessibilityInfo.announceForAccessibility(detail === null ? label : `${label}. ${detail}`);
  }, [label, detail]);
}

const styles = StyleSheet.create({
  wrap: { gap: SPACE.sm },
  status: {
    minHeight: PRIMARY_TOUCH,
    justifyContent: "center",
    gap: SPACE.xs,
    padding: SPACE.md,
    borderWidth: 2,
    borderRadius: RADIUS,
    backgroundColor: COLOR.surface,
  },
  headline: { flexDirection: "row", alignItems: "center", gap: SPACE.sm },
  icon: { fontSize: FONT.large, fontWeight: "700", minWidth: SPACE.lg, textAlign: "center" },
  label: { flexShrink: 1, fontSize: FONT.large, fontWeight: "700" },
  detail: { color: COLOR.text, fontSize: FONT.body },
  tip: { color: COLOR.muted, fontSize: FONT.small },
});
