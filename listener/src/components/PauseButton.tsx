/** Pausing the commentary on purpose (UI rule 1.3): one tap, no
 * question asked, and it stays paused until the listener plays it again. */

import { Pressable, StyleSheet, Text } from "react-native";

import { COLOR, FONT, PRIMARY_TOUCH, RADIUS, SPACE } from "@/theme";

export function PauseButton({ isPaused, onPress }: { isPaused: boolean; onPress(): void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.button}>
      <Text style={styles.label}>{isPaused ? "Play commentary" : "Pause commentary"}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: PRIMARY_TOUCH,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: SPACE.md,
    borderRadius: RADIUS,
    backgroundColor: COLOR.raised,
  },
  label: { color: COLOR.text, fontSize: FONT.large, fontWeight: "700" },
});
