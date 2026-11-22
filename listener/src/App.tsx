/** The listener app: pick a game, pick a commentator, listen. No account
 * needed (UI rule 7.2): listening runs on a guest token (hooks/useAccess.tsx). */

import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AccessProvider } from "@/hooks/useAccess";
import { useRoutes } from "@/hooks/useRoutes";
import { CommentatorsScreen } from "@/screens/CommentatorsScreen";
import { GamesScreen } from "@/screens/GamesScreen";
import { ListenScreen } from "@/screens/ListenScreen";

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <AccessProvider>
        <Navigator />
      </AccessProvider>
    </SafeAreaProvider>
  );
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
