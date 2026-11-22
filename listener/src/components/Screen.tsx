/** Every screen's frame: safe-area padding, a title (and a line under it),
 * optional back and header actions, and a body that scrolls, so nothing is
 * clipped when the phone's text is made larger (UI rule 10). Lists pass
 * `scrolls={false}` and scroll themselves. */

import type { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { COLOR, FONT, MIN_TOUCH, SPACE } from "@/theme";

export interface HeaderAction {
  label: string;
  onPress(): void;
}

interface ScreenProps {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  action?: HeaderAction;
  scrolls?: boolean;
  children: ReactNode;
}

export function Screen({ title, subtitle, onBack, action, scrolls = true, children }: ScreenProps) {
  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.header}>
        {onBack ? <TextButton label="Back" onPress={onBack} /> : null}
        <View style={styles.titles}>
          <Text style={styles.title} accessibilityRole="header">
            {title}
          </Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
        {action ? <TextButton label={action.label} onPress={action.onPress} /> : null}
      </View>
      {scrolls ? (
        <ScrollView contentContainerStyle={styles.scrolling}>{children}</ScrollView>
      ) : (
        <View style={styles.body}>{children}</View>
      )}
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
  titles: { flex: 1, gap: SPACE.xs },
  title: { color: COLOR.text, fontSize: FONT.title, fontWeight: "700" },
  subtitle: { color: COLOR.muted, fontSize: FONT.body },
  body: { flex: 1, paddingHorizontal: SPACE.md },
  scrolling: { gap: SPACE.lg, paddingHorizontal: SPACE.md, paddingBottom: SPACE.xl },
  textButton: { minHeight: MIN_TOUCH, minWidth: MIN_TOUCH, justifyContent: "center" },
  textButtonLabel: { color: COLOR.accentText, fontSize: FONT.body, fontWeight: "600" },
});
