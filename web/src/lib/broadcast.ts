/** Sending the commentator's microphone to the stream's LiveKit room.
 * Loaded only when going live (rule 69): livekit-client is the studio's
 * largest dependency. Everything LiveKit-specific in the browser is here. */

import { Room, RoomEvent, Track } from "livekit-client";

import type { RoomAccess } from "@commentary-sync/client/schema";

export type ConnectionState = "connecting" | "live" | "reconnecting" | "disconnected";

export interface Broadcast {
  stop(): Promise<void>;
}

const TRACK_NAME = "commentary";

/** Join the room with a publisher token and publish `microphone`. LiveKit
 * reconnects on its own after a network blip; `onState` follows it. */
export async function startBroadcast(
  access: RoomAccess,
  microphone: MediaStreamTrack,
  onState: (state: ConnectionState) => void,
): Promise<Broadcast> {
  const room = new Room();
  room
    .on(RoomEvent.Reconnecting, () => onState("reconnecting"))
    .on(RoomEvent.Reconnected, () => onState("live"))
    .on(RoomEvent.Disconnected, () => onState("disconnected"));
  onState("connecting");
  try {
    await room.connect(access.url, access.token);
    // The token allows the microphone source only; any other is refused.
    await room.localParticipant.publishTrack(microphone, { source: Track.Source.Microphone, name: TRACK_NAME });
  } catch (error) {
    room.removeAllListeners();
    await room.disconnect(false); // the microphone stays open: useMicrophone owns it
    throw error;
  }
  onState("live");
  return {
    async stop() {
      room.removeAllListeners();
      await room.disconnect(false); // the microphone stays open: useMicrophone owns it
    },
  };
}
