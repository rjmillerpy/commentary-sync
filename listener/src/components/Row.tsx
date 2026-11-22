/** One tappable line in a list: a title, detail lines, and an optional
 * "live" badge (a dot and the word: colour is never the only signal). */

import { memo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { COLOR, FONT, MIN_TOUCH, RADIUS, SPACE, STATUS } from "@/theme";

interface RowProps {
  title: string;
  /** Lines under the title, most important first (UI rule 7.1). */
  details: string[];
  isLive?: boolean;
  onPress(): void;
}

export const Row = memo(function Row({ title, details, isLive = false, onPress }: RowProps) {
  const spoken = [title, ...details, ...(isLive ? ["live"] : [])].join(", ");
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={spoken} onPress={onPress} style={styles.row}>
      <View style={styles.text}>
        <Text style={styles.title}>{title}</Text>
        {details.map((detail) => (
          <Text key={detail} style={styles.detail}>
            {detail}
          </Text>
        ))}
      </View>
      {isLive ? <Text style={styles.badge}>● LIVE</Text> : null}
    </Pressable>
  );
});

/** A row-shaped placeholder while a list loads (UI rule 8: never a blank screen). */
export function PlaceholderRows({ count = 3 }: { count?: number }) {
  return (
    <View accessible accessibilityLabel="Loading" accessibilityRole="progressbar">
      {Array.from({ length: count }, (_unused, index) => (
        <View key={index} style={[styles.row, styles.placeholder]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: SPACE.sm,
    minHeight: MIN_TOUCH,
    padding: SPACE.md,
    marginBottom: SPACE.sm,
    borderRadius: RADIUS,
    backgroundColor: COLOR.surface,
  },
  placeholder: { height: MIN_TOUCH + SPACE.lg },
  text: { flex: 1, gap: SPACE.xs },
  title: { color: COLOR.text, fontSize: FONT.body, fontWeight: "600" },
  detail: { color: COLOR.muted, fontSize: FONT.small },
  badge: { color: STATUS.live, fontSize: FONT.small, fontWeight: "700" },
});
