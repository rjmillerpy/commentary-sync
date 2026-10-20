/** Listening to one commentator, delayed to match the listener's TV, and
 * kept that way (hooks/useListenSession.ts). */

import type { SportsEvent, Stream } from "@commentary-sync/client/schema";
import { StyleSheet, Text } from "react-native";

import { DelayControl } from "@/components/DelayControl";
import { Notice } from "@/components/Notice";
import { Screen } from "@/components/Screen";
import { SyncPanel } from "@/components/SyncPanel";
import type { Playback } from "@/hooks/useDelayedPlayback";
import { useListenSession } from "@/hooks/useListenSession";
import { formatSeconds } from "@/lib/delay";
import { COLOR, FONT } from "@/theme";

interface ListenScreenProps {
  game: SportsEvent;
  stream: Stream;
  onBack(): void;
}

const OFFLINE = "No connection. The commentary picks up again at the same delay when it's back.";

export function ListenScreen({ game, stream, onBack }: ListenScreenProps) {
  const session = useListenSession(stream);
  const { playlist, playback, sync } = session;
  const name = stream.commentator.display_name;

  if (session.hasEnded) {
    return (
      <Screen title={name} onBack={onBack}>
        <Notice text={`${name} has ended the stream.`} />
      </Screen>
    );
  }
  return (
    <Screen title={name} onBack={onBack}>
      <Text style={styles.game}>{game.title}</Text>
      {session.isOnline ? null : <Notice text={OFFLINE} isError />}
      {playlist.kind === "failed" ? <Notice text={playlist.detail} isError /> : null}
      {playlist.kind === "waiting" ? <Notice text={`Waiting for ${name}'s audio…`} /> : null}
      {playlist.kind === "ready" ? <Notice text={status(playback, session.delay)} /> : null}
      <DelayControl delay={session.delay} onChange={session.setDelay} />
      <SyncPanel
        state={sync.state}
        onSync={() => void sync.start()}
        autoSync={session.autoSync}
        onAutoSyncChange={session.setAutoSync}
      />
    </Screen>
  );
}

function status({ phase, behind }: Playback, delay: number): string {
  if (phase === "reconnecting") return "Reconnecting… the commentary picks up again at the same delay.";
  if (phase === "loading" || behind === null) return "Starting…";
  if (phase === "holding") return `Building up the delay: ${formatSeconds(behind)} of ${formatSeconds(delay)}`;
  return `Playing ${formatSeconds(behind)} behind live`;
}

const styles = StyleSheet.create({
  game: { color: COLOR.muted, fontSize: FONT.body },
});
