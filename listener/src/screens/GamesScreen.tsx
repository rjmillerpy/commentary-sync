/** The games a listener can hear commentary on: on now, or coming up. */

import { useSession } from "@commentary-sync/client/react";
import type { SportsEvent } from "@commentary-sync/client/schema";
import { useCallback } from "react";
import { FlatList, RefreshControl } from "react-native";

import { Notice } from "@/components/Notice";
import { Row } from "@/components/Row";
import { Screen } from "@/components/Screen";
import { useLoad } from "@/hooks/useLoad";
import { api } from "@/lib/api";

const OPEN = new Set<SportsEvent["status"]>(["live", "scheduled"]);
const START_FORMAT: Intl.DateTimeFormatOptions = { weekday: "short", hour: "numeric", minute: "2-digit" };

export function GamesScreen({ onPick }: { onPick(game: SportsEvent): void }) {
  const { signOut } = useSession();
  const load = useCallback(async () => (await api.upcomingEvents()).items.filter((game) => OPEN.has(game.status)), []);
  const { data: games, error, isLoading, reload } = useLoad(load);

  return (
    <Screen title="Games" action={{ label: "Sign out", onPress: () => void signOut() }}>
      {error ? <Notice text={error} isError /> : null}
      <FlatList
        data={games ?? []}
        keyExtractor={(game) => game.id}
        renderItem={({ item }) => (
          <Row title={item.title} detail={describe(item)} badge={item.status === "live" ? "LIVE" : undefined} onPress={() => onPick(item)} />
        )}
        ListEmptyComponent={isLoading ? undefined : <Notice text="No games on or coming up." />}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={reload} />}
      />
    </Screen>
  );
}

function describe(game: SportsEvent): string {
  const when = new Date(game.starts_at).toLocaleString([], START_FORMAT);
  return [game.league.toUpperCase(), when, ...game.networks].join(" · ");
}
