/** livekit-client, faked: the boundary to the media server (WebRTC, which
 * jsdom doesn't have). Tests use it with
 *   jest.mock("livekit-client", () => jest.requireActual("../_fakeLiveKit").liveKitModule);
 */

type Handler = () => void;

export const control = {
  rooms: [] as FakeRoom[],
  connectFailure: null as Error | null,
  publishFailure: null as Error | null,
  reset() {
    this.rooms.length = 0;
    this.connectFailure = null;
    this.publishFailure = null;
  },
};

export class FakeRoom {
  readonly handlers = new Map<string, Handler>();
  connectedTo: { url: string; token: string } | null = null;
  disconnectedWith: boolean | undefined | null = null;
  readonly published: { track: unknown; options: unknown }[] = [];
  readonly localParticipant = {
    publishTrack: async (track: unknown, options: unknown) => {
      if (control.publishFailure !== null) throw control.publishFailure;
      this.published.push({ track, options });
    },
  };

  constructor() {
    control.rooms.push(this);
  }
  on(event: string, handler: Handler): this {
    this.handlers.set(event, handler);
    return this;
  }
  emit(event: string): void {
    this.handlers.get(event)?.();
  }
  removeAllListeners(): void {
    this.handlers.clear();
  }
  async connect(url: string, token: string): Promise<void> {
    if (control.connectFailure !== null) throw control.connectFailure;
    this.connectedTo = { url, token };
  }
  async disconnect(stopTracks?: boolean): Promise<void> {
    this.disconnectedWith = stopTracks;
  }
}

export const liveKitModule = {
  Room: FakeRoom,
  RoomEvent: { Reconnecting: "reconnecting", Reconnected: "reconnected", Disconnected: "disconnected" },
  Track: { Source: { Microphone: "microphone" } },
};
