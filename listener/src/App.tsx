/** The listener app: sign in, pick a game, pick a commentator, listen. */

import { SessionProvider, useSession } from "@commentary-sync/client/react";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useRoutes } from "@/hooks/useRoutes";
import { Session } from "@/lib/session";
import { CommentatorsScreen } from "@/screens/CommentatorsScreen";
import { GamesScreen } from "@/screens/GamesScreen";
import { ListenScreen } from "@/screens/ListenScreen";
import { SignInScreen } from "@/screens/SignInScreen";
import { COLOR } from "@/theme";

const createSession = () => new Session();

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <SessionProvider createSession={createSession}>
        <Main />
      </SessionProvider>
    </SafeAreaProvider>
  );
}

function Main() {
  const { status } = useSession();
  if (status === "restoring") {
    return (
      <View style={styles.restoring}>
        <ActivityIndicator accessibilityLabel="Signing in" color={COLOR.accent} />
      </View>
    );
  }
  return status === "signed-in" ? <Navigator /> : <SignInScreen />;
}

function Navigator() {
  const { current, open, back } = useRoutes();
  switch (current.name) {
    case "games":
      return <GamesScreen onPick={(game) => open({ name: "commentators", game })} />;
    case "commentators":
      return (
        <CommentatorsScreen game={current.game} onBack={back} onPick={(stream) => open({ name: "listen", game: current.game, stream })} />
      );
    case "listen":
      return <ListenScreen game={current.game} stream={current.stream} onBack={back} />;
  }
}

const styles = StyleSheet.create({
  restoring: { flex: 1, justifyContent: "center", backgroundColor: COLOR.background },
});
