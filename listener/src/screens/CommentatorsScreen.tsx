/** Who is commentating one game right now. */

import type { SportsEvent, Stream } from "@commentary-sync/client/schema";
import { useCallback } from "react";
import { FlatList, RefreshControl } from "react-native";

import { Notice } from "@/components/Notice";
import { Row } from "@/components/Row";
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
    <Screen title={game.title} onBack={onBack}>
      {error ? <Notice text={error} isError /> : null}
      <FlatList
        data={streams ?? []}
        keyExtractor={(stream) => stream.id}
        renderItem={({ item }) => (
          <Row title={item.commentator.display_name} detail={describe(item)} badge="LIVE" onPress={() => onPick(item)} />
        )}
        ListEmptyComponent={isLoading ? undefined : <Notice text="Nobody is commentating this game yet. Pull to check again." />}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={reload} />}
      />
    </Screen>
  );
}

function describe(stream: Stream): string {
  const handle = `@${stream.commentator.handle}`;
  return stream.listeners === null ? handle : `${handle} · ${stream.listeners} listening`;
}
