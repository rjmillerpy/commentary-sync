/** Who is commentating one game right now. */

import type { SportsEvent, Stream } from "@commentary-sync/client/schema";
import { useCallback } from "react";
import { FlatList } from "react-native";

import { Notice } from "@/components/Notice";
import { PlaceholderRows, Row } from "@/components/Row";
import { Screen } from "@/components/Screen";
import { useLoad } from "@/hooks/useLoad";
import { api } from "@/lib/api";

interface CommentatorsScreenProps {
  game: SportsEvent;
  onPick(stream: Stream): void;
  onBack(): void;
}

export function CommentatorsScreen({ game, onPick, onBack }: CommentatorsScreenProps) {
  const load = useCallback(async () => (await api.liveStreamsOn(game.id)).items, [game.id]);
  const { data: streams, error, isLoading, reload } = useLoad(load);

  return (
    <Screen title={game.title} subtitle="Pick a commentator" onBack={onBack} action={{ label: "Refresh", onPress: reload }} scrolls={false}>
      {error ? <Notice text={`Couldn't load the commentators: ${error}`} isError action={{ label: "Try again", onPress: reload }} /> : null}
      {isLoading && streams === null ? <PlaceholderRows /> : null}
      <FlatList
        data={streams ?? []}
        keyExtractor={(stream) => stream.id}
        renderItem={({ item }) => (
          <Row title={item.commentator.display_name} details={[describe(item)]} isLive onPress={() => onPick(item)} />
        )}
        ListEmptyComponent={
          isLoading || error ? undefined : (
            <Notice text="Nobody is commentating this game yet." action={{ label: "Check again", onPress: reload }} />
          )
        }
      />
    </Screen>
  );
}

function describe(stream: Stream): string {
  const handle = `@${stream.commentator.handle}`;
  if (stream.listeners === null) return handle;
  return `${handle} · ${stream.listeners} ${stream.listeners === 1 ? "listener" : "listeners"}`;
}
