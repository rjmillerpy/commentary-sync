/** A value with a step down and a step up either side of it: the volume and
 * the fine-tune. Each button says in words what it does. */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { COLOR, DIMMED, FONT, MIN_TOUCH, RADIUS, SPACE } from "@/theme";

export interface Step {
  label: string;
  /** What a screen reader says, when the label alone isn't enough. */
  accessibilityLabel?: string;
  onPress(): void;
  disabled?: boolean;
}

interface StepperProps {
  title: string;
  value: string;
  /** What a screen reader says for the value. */
  valueLabel: string;
  down: Step;
  up: Step;
  hint?: string;
}

export function Stepper({ title, value, valueLabel, down, up, hint }: StepperProps) {
  return (
    <View style={styles.stepper}>
      <Text style={styles.title}>{title}</Text>
      <View style={styles.row}>
        <StepButton {...down} />
        <Text style={styles.value} accessibilityLabel={valueLabel}>
          {value}
        </Text>
        <StepButton {...up} />
      </View>
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

export function StepButton({ label, accessibilityLabel, onPress, disabled = false }: Step) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.step, disabled && styles.disabled]}
    >
      <Text style={styles.stepLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stepper: { gap: SPACE.sm },
  title: { color: COLOR.muted, fontSize: FONT.small },
  row: { flexDirection: "row", alignItems: "center", gap: SPACE.sm },
  value: { flex: 1, color: COLOR.text, fontSize: FONT.large, fontWeight: "700", textAlign: "center" },
  step: {
    minWidth: MIN_TOUCH,
    minHeight: MIN_TOUCH,
    paddingHorizontal: SPACE.md,
    justifyContent: "center",
    alignItems: "center",
    borderRadius: RADIUS,
    backgroundColor: COLOR.raised,
  },
  disabled: { opacity: DIMMED },
  stepLabel: { color: COLOR.text, fontSize: FONT.body, fontWeight: "600" },
  hint: { color: COLOR.muted, fontSize: FONT.small },
});
