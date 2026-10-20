/** One tappable line in a list: a title, a detail line, and an optional badge. */

import { memo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { COLOR, FONT, MIN_TOUCH, RADIUS, SPACE } from "@/theme";

interface RowProps {
  title: string;
  detail: string;
  badge?: string;
  onPress(): void;
}

export const Row = memo(function Row({ title, detail, badge, onPress }: RowProps) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={title} onPress={onPress} style={styles.row}>
      <View style={styles.text}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.detail}>{detail}</Text>
      </View>
      {badge ? <Text style={styles.badge}>{badge}</Text> : null}
    </Pressable>
  );
});

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    minHeight: MIN_TOUCH,
    padding: SPACE.md,
    marginBottom: SPACE.sm,
    borderRadius: RADIUS,
    backgroundColor: COLOR.surface,
  },
  text: { flex: 1, gap: SPACE.xs },
  title: { color: COLOR.text, fontSize: FONT.body, fontWeight: "600" },
  detail: { color: COLOR.muted, fontSize: FONT.small },
  badge: { color: COLOR.live, fontSize: FONT.small, fontWeight: "700" },
});
