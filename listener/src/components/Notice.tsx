/** A line of status text: an empty list, a wait, or something that went wrong. */

import { StyleSheet, Text } from "react-native";

import { COLOR, FONT, SPACE } from "@/theme";

export function Notice({ text, isError = false }: { text: string; isError?: boolean }) {
  return (
    <Text style={[styles.notice, isError && styles.error]} accessibilityRole={isError ? "alert" : "text"}>
      {text}
    </Text>
  );
}

const styles = StyleSheet.create({
  notice: { color: COLOR.muted, fontSize: FONT.body, paddingVertical: SPACE.md },
  error: { color: COLOR.danger },
});
