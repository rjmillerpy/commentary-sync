/** What most listeners never need, folded away: turning sync off and setting
 * the delay by hand, and the exact numbers behind the sync status
 * (UI rule 1.1: the offset belongs in a details panel, not the main view). */

import { useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";

import { DelayControl } from "@/components/DelayControl";
import { TextButton } from "@/components/Screen";
import { formatOffset, formatSeconds } from "@/lib/delay";
import { COLOR, FONT, MIN_TOUCH, SPACE } from "@/theme";

interface MoreOptionsProps {
  isSyncOn: boolean;
  onSyncOn(on: boolean): void;
  baseDelay: number;
  onBaseDelay(seconds: number): void;
  fineTune: number;
  /** Seconds behind the commentator right now, once known. */
  behind: number | null;
}

export function MoreOptions(props: MoreOptionsProps) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <View style={styles.more}>
      <TextButton label={isOpen ? "Fewer options" : "More options"} onPress={() => setIsOpen(!isOpen)} />
      {isOpen ? <Options {...props} /> : null}
    </View>
  );
}

function Options({ isSyncOn, onSyncOn, baseDelay, onBaseDelay, fineTune, behind }: MoreOptionsProps) {
  return (
    <View style={styles.options}>
      <View style={styles.switchRow}>
        <Text style={styles.text}>Keep in sync with my TV</Text>
        <Switch accessibilityLabel="Keep in sync with my TV" value={isSyncOn} onValueChange={onSyncOn} />
      </View>
      {isSyncOn ? null : <DelayControl delay={baseDelay} onChange={onBaseDelay} />}
      <Text style={styles.title}>Sync details</Text>
      <Text style={styles.text}>{`Delay: ${formatSeconds(baseDelay)}${isSyncOn ? " (from your TV)" : " (set by you)"}`}</Text>
      <Text style={styles.text}>{`Fine-tune: ${formatOffset(fineTune)}`}</Text>
      <Text style={styles.text}>{behind === null ? "Behind the commentator: not known yet" : `Behind the commentator: ${formatSeconds(behind)}`}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  more: { gap: SPACE.sm },
  options: { gap: SPACE.sm, paddingBottom: SPACE.lg },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: MIN_TOUCH, gap: SPACE.sm },
  title: { color: COLOR.muted, fontSize: FONT.small, paddingTop: SPACE.sm },
  text: { flexShrink: 1, color: COLOR.text, fontSize: FONT.body },
});
