/** Setting the delay by hand, with sync off: how far behind real time the
 * commentary plays, nudged in big and small steps until it matches the TV. */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { clampDelay, DELAY_NUDGES, formatSeconds } from "@/lib/delay";
import { COLOR, FONT, MIN_TOUCH, RADIUS, SPACE } from "@/theme";

interface DelayControlProps {
  delay: number;
  onChange(delay: number): void;
}

export function DelayControl({ delay, onChange }: DelayControlProps) {
  return (
    <View style={styles.control}>
      <Text style={styles.label}>Delay</Text>
      <Text style={styles.value} accessibilityLabel={`Delay ${formatSeconds(delay)}`}>
        {formatSeconds(delay)}
      </Text>
      <View style={styles.steps}>
        {DELAY_NUDGES.map((step) => (
          <Pressable
            key={step}
            accessibilityRole="button"
            accessibilityLabel={`${step > 0 ? "More" : "Less"} delay, ${Math.abs(step)} ${Math.abs(step) === 1 ? "second" : "seconds"}`}
            onPress={() => onChange(clampDelay(delay + step))}
            style={styles.step}
          >
            <Text style={styles.stepLabel}>{`${step > 0 ? "+" : "−"}${Math.abs(step)}`}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.hint}>Commentary ahead of your TV? More delay. Behind it? Less.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  control: { alignItems: "center", gap: SPACE.sm, paddingVertical: SPACE.md },
  label: { color: COLOR.muted, fontSize: FONT.small },
  value: { color: COLOR.text, fontSize: FONT.big, fontWeight: "700" },
  steps: { flexDirection: "row", gap: SPACE.sm },
  step: {
    minWidth: MIN_TOUCH,
    minHeight: MIN_TOUCH,
    paddingHorizontal: SPACE.md,
    justifyContent: "center",
    alignItems: "center",
    borderRadius: RADIUS,
    backgroundColor: COLOR.raised,
  },
  stepLabel: { color: COLOR.text, fontSize: FONT.body, fontWeight: "600" },
  hint: { color: COLOR.muted, fontSize: FONT.small, textAlign: "center" },
});
