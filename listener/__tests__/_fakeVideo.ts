/** expo-video's player, faked: the phone's media player is a boundary. The
 * fake plays a live HLS recording on a timeline the test moves by hand:
 * `currentOffsetFromLive` is how far behind live it is, and seeking or
 * pausing changes it the way a real player's would. */

import { useState } from "react";

export class FakePlayer {
  status: "idle" | "loading" | "readyToPlay" | "error" = "readyToPlay";
  playing = false;
  staysActiveInBackground = false;
  showNowPlayingNotification = false;
  /** Seconds into the recording. */
  currentTime = 0;
  /** Seconds behind live; null until the player has read the playlist's clock. */
  currentOffsetFromLive: number | null = null;
  muted = false;
  readonly seeks: number[] = [];
  /** Sources reloaded after a failure, in order. */
  readonly reloads: string[] = [];
  /** While true, a reload fails too (the connection is still down). */
  keepsFailing = false;

  constructor(readonly source: string | null) {}

  async replaceAsync(source: string): Promise<void> {
    this.reloads.push(source);
    if (this.keepsFailing) throw new Error("still offline");
    this.status = "readyToPlay";
  }

  play(): void {
    this.playing = true;
  }

  pause(): void {
    this.playing = false;
  }

  seekBy(seconds: number): void {
    this.seeks.push(seconds);
    this.currentTime += seconds;
    if (this.currentOffsetFromLive !== null) this.currentOffsetFromLive -= seconds;
  }

  /** `seconds` of real time pass: live moves on, and so does a playing player. */
  advance(seconds: number): void {
    if (this.currentOffsetFromLive !== null && !this.playing) this.currentOffsetFromLive += seconds;
    if (this.playing) this.currentTime += seconds;
  }
}

/** Every player the app has made, newest last. */
export const players: FakePlayer[] = [];

export function useVideoPlayer(source: string | null, setup?: (player: FakePlayer) => void): FakePlayer {
  // One player per source, as expo-video does: a new source is a new player.
  const [bySource] = useState(() => new Map<string | null, FakePlayer>());
  let player = bySource.get(source);
  if (player === undefined) {
    player = new FakePlayer(source);
    setup?.(player);
    bySource.set(source, player);
    players.push(player);
  }
  return player;
}

export function latestPlayer(): FakePlayer {
  const player = players.at(-1);
  if (player === undefined) throw new Error("no player was made");
  return player;
}

export function reset(): void {
  players.length = 0;
}
