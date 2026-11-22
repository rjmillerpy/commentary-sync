/** Listening to one commentator, delayed to match the listener's TV, and
 * kept that way (hooks/useListenSession.ts). Top to bottom: the one sync
 * status (which is also the way to fix it), pause, volume, fine-tune, and
 * everything else folded away. */

import type { SportsEvent, Stream } from "@commentary-sync/client/schema";

import { FineTune } from "@/components/FineTune";
import { MoreOptions } from "@/components/MoreOptions";
import { Notice } from "@/components/Notice";
import { PauseButton } from "@/components/PauseButton";
import { Screen } from "@/components/Screen";
import { SyncIndicator } from "@/components/SyncIndicator";
import { VolumeControl } from "@/components/VolumeControl";
import { useListenSession } from "@/hooks/useListenSession";
import { useSyncTip } from "@/hooks/useSyncTip";

interface ListenScreenProps {
  game: SportsEvent;
  stream: Stream;
  onBack(): void;
}

export function ListenScreen({ game, stream, onBack }: ListenScreenProps) {
  const session = useListenSession(stream);
  const name = stream.commentator.display_name;
  const showTip = useSyncTip(session.status.kind);

  if (session.hasEnded) {
    return (
      <Screen title={name} subtitle={game.title} onBack={onBack}>
        <Notice text={`${name} has ended the stream.`} action={{ label: "Pick another commentator", onPress: onBack }} />
      </Screen>
    );
  }
  const { playlist } = session;
  return (
    <Screen title={name} subtitle={game.title} onBack={onBack}>
      {playlist.kind === "failed" ? (
        <Notice text={`Can't play this commentary: ${playlist.detail}`} isError action={{ label: "Pick another commentator", onPress: onBack }} />
      ) : null}
      {playlist.kind === "waiting" ? <Notice text={`Waiting for ${name}'s audio to start…`} /> : null}
      <SyncIndicator status={session.status} onAct={session.act} showTip={showTip} />
      <PauseButton isPaused={session.isPaused} onPress={session.togglePause} />
      <VolumeControl volume={session.volume} onVolume={session.setVolume} isMuted={session.isMuted} onMute={session.setIsMuted} />
      <FineTune value={session.fineTune} onChange={session.setFineTune} />
      <MoreOptions
        isSyncOn={session.isSyncOn}
        onSyncOn={session.setIsSyncOn}
        baseDelay={session.baseDelay}
        onBaseDelay={session.setBaseDelay}
        fineTune={session.fineTune}
        behind={session.behind}
      />
    </Screen>
  );
}
