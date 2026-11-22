/** The first screen: games on now or coming up, the ones with commentary
 * first. No sign-in in front of it (UI rule 7.2). */

import type { SportsEvent } from "@commentary-sync/client/schema";
import { useCallback } from "react";
import { SectionList, StyleSheet, Text } from "react-native";

import { Notice } from "@/components/Notice";
import { PlaceholderRows, Row } from "@/components/Row";
import { Screen } from "@/components/Screen";
import { useLoad } from "@/hooks/useLoad";
import { api } from "@/lib/api";
import { commentatorCount, type GameEntry, sectionGames, whenAndWhere } from "@/lib/games";
import { COLOR, FONT, SPACE } from "@/theme";

export function GamesScreen({ onPick }: { onPick(game: SportsEvent): void }) {
  const load = useCallback(async () => {
    const [games, live] = await Promise.all([api.upcomingEvents(), api.liveStreams()]);
    return sectionGames(games.items, live.items);
  }, []);
  const { data, error, isLoading, reload } = useLoad(load);
  const sections = data === null ? [] : [
    { title: "Commentary live now", data: data.withCommentary },
    { title: "Other games", data: data.others },
  ].filter((section) => section.data.length > 0);

  return (
    <Screen title="Games" subtitle="Pick the game on your TV" action={{ label: "Refresh", onPress: reload }} scrolls={false}>
      {error ? <Notice text={`Couldn't load the games: ${error}`} isError action={{ label: "Try again", onPress: reload }} /> : null}
      {isLoading && data === null ? <PlaceholderRows /> : null}
      <SectionList
        sections={sections}
        keyExtractor={(entry) => entry.game.id}
        renderSectionHeader={({ section }) => <Text style={styles.section}>{section.title}</Text>}
        renderItem={({ item }) => <GameRow entry={item} onPick={onPick} />}
        ListEmptyComponent={isLoading || error ? undefined : <Notice text="No games on or coming up in the next few days." />}
        stickySectionHeadersEnabled={false}
      />
    </Screen>
  );
}

function GameRow({ entry, onPick }: { entry: GameEntry; onPick(game: SportsEvent): void }) {
  const { game, commentators } = entry;
  return (
    <Row
      title={game.title}
      details={[commentatorCount(commentators), whenAndWhere(game)]}
      isLive={game.status === "live"}
      onPress={() => onPick(game)}
    />
  );
}

const styles = StyleSheet.create({
  section: { color: COLOR.muted, fontSize: FONT.small, fontWeight: "700", paddingVertical: SPACE.sm },
});
