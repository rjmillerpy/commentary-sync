/** Every screen's frame: safe-area padding, a title, and optional back and
 * header actions. */

import type { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { COLOR, FONT, MIN_TOUCH, SPACE } from "@/theme";

export interface HeaderAction {
  label: string;
  onPress(): void;
}

interface ScreenProps {
  title: string;
  onBack?: () => void;
  action?: HeaderAction;
  children: ReactNode;
}

export function Screen({ title, onBack, action, children }: ScreenProps) {
  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.header}>
        {onBack ? <TextButton label="Back" onPress={onBack} /> : null}
        <Text style={styles.title} accessibilityRole="header" numberOfLines={2}>
          {title}
        </Text>
        {action ? <TextButton label={action.label} onPress={action.onPress} /> : null}
      </View>
      <View style={styles.body}>{children}</View>
    </SafeAreaView>
  );
}

export function TextButton({ label, onPress }: HeaderAction) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.textButton} hitSlop={SPACE.sm}>
      <Text style={styles.textButtonLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLOR.background },
  header: { flexDirection: "row", alignItems: "center", gap: SPACE.sm, padding: SPACE.md },
  title: { flex: 1, color: COLOR.text, fontSize: FONT.title, fontWeight: "700" },
  body: { flex: 1, paddingHorizontal: SPACE.md },
  textButton: { minHeight: MIN_TOUCH, justifyContent: "center" },
  textButtonLabel: { color: COLOR.accent, fontSize: FONT.body },
});
