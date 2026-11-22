/** A line of status text: an empty list, a wait, or something that went
 * wrong. A problem says what happened and what it means, and offers one way
 * out (UI rule 9), never a dialog. */

import { StyleSheet, Text, View } from "react-native";

import { type HeaderAction, TextButton } from "@/components/Screen";
import { COLOR, FONT, SPACE, STATUS } from "@/theme";

interface NoticeProps {
  text: string;
  isError?: boolean;
  action?: HeaderAction;
}

export function Notice({ text, isError = false, action }: NoticeProps) {
  return (
    <View style={styles.notice}>
      <Text style={[styles.text, isError && styles.error]} accessibilityRole={isError ? "alert" : "text"}>
        {text}
      </Text>
      {action ? <TextButton {...action} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  notice: { paddingVertical: SPACE.md, gap: SPACE.xs, alignItems: "flex-start" },
  text: { color: COLOR.muted, fontSize: FONT.body },
  error: { color: STATUS.error },
});
