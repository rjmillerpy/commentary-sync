/** Sign in, or create an account: listening needs one (the API hands
 * playlists only to signed-in accounts). */

import { ApiError } from "@commentary-sync/client/api";
import { useSession } from "@commentary-sync/client/react";
import { MAX_DISPLAY_NAME_LENGTH, MAX_PASSWORD_LENGTH } from "@commentary-sync/client/schema";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput } from "react-native";

import { Notice } from "@/components/Notice";
import { Screen, TextButton } from "@/components/Screen";
import { COLOR, FONT, MIN_TOUCH, RADIUS, SPACE } from "@/theme";

const FAILED = "Couldn't sign in; try again.";

export function SignInScreen() {
  const { signIn, register } = useSession();
  const [isRegistering, setIsRegistering] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const submit = async () => {
    setIsBusy(true);
    setError(null);
    try {
      if (isRegistering) await register({ email, password, display_name: name });
      else await signIn(email, password);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : FAILED);
      setIsBusy(false); // on success this screen is gone
    }
  };

  return (
    <Screen title={isRegistering ? "Create an account" : "Sign in"}>
      {isRegistering ? <Field label="Display name" value={name} onChange={setName} maxLength={MAX_DISPLAY_NAME_LENGTH} /> : null}
      <Field label="Email" value={email} onChange={setEmail} kind="email" />
      <Field label="Password" value={password} onChange={setPassword} kind="password" maxLength={MAX_PASSWORD_LENGTH} />
      {error ? <Notice text={error} isError /> : null}
      <Pressable accessibilityRole="button" disabled={isBusy} onPress={() => void submit()} style={styles.submit}>
        <Text style={styles.submitLabel}>{isRegistering ? "Create account" : "Sign in"}</Text>
      </Pressable>
      <TextButton
        label={isRegistering ? "I have an account" : "Create an account instead"}
        onPress={() => setIsRegistering((current) => !current)}
      />
    </Screen>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange(value: string): void;
  kind?: "email" | "password";
  maxLength?: number;
}

function Field({ label, value, onChange, kind, maxLength }: FieldProps) {
  return (
    <>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        maxLength={maxLength}
        autoCapitalize={kind ? "none" : "words"}
        autoComplete={kind === "email" ? "email" : kind === "password" ? "password" : "name"}
        keyboardType={kind === "email" ? "email-address" : "default"}
        secureTextEntry={kind === "password"}
        style={styles.input}
        placeholderTextColor={COLOR.muted}
      />
    </>
  );
}

const styles = StyleSheet.create({
  label: { color: COLOR.muted, fontSize: FONT.small, marginTop: SPACE.md, marginBottom: SPACE.xs },
  input: {
    minHeight: MIN_TOUCH,
    paddingHorizontal: SPACE.md,
    borderRadius: RADIUS,
    backgroundColor: COLOR.surface,
    color: COLOR.text,
    fontSize: FONT.body,
  },
  submit: {
    minHeight: MIN_TOUCH,
    marginVertical: SPACE.lg,
    justifyContent: "center",
    alignItems: "center",
    borderRadius: RADIUS,
    backgroundColor: COLOR.accent,
  },
  submitLabel: { color: COLOR.text, fontSize: FONT.body, fontWeight: "700" },
});
