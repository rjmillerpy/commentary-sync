import { startBroadcast } from "@/lib/broadcast";
import { control } from "../_fakeLiveKit";
import { ROOM } from "../_fakeApi";

jest.mock("livekit-client", () => jest.requireActual("../_fakeLiveKit").liveKitModule);

const microphone = { kind: "audio" } as MediaStreamTrack;

beforeEach(() => control.reset());

test("joins the room with the API's token and publishes the mic as the microphone source", async () => {
  const states: string[] = [];
  await startBroadcast(ROOM, microphone, (state) => states.push(state));
  const room = control.rooms[0]!;
  expect(room.connectedTo).toEqual({ url: ROOM.url, token: ROOM.token });
  expect(room.published).toEqual([{ track: microphone, options: { source: "microphone", name: "commentary" } }]);
  expect(states).toEqual(["connecting", "live"]);
});

test("follows LiveKit reconnecting on its own", async () => {
  const states: string[] = [];
  await startBroadcast(ROOM, microphone, (state) => states.push(state));
  const room = control.rooms[0]!;
  room.emit("reconnecting");
  room.emit("reconnected");
  room.emit("disconnected");
  expect(states.slice(2)).toEqual(["reconnecting", "live", "disconnected"]);
});

test("stopping leaves the room but not the microphone, which the mic check still uses", async () => {
  const states: string[] = [];
  const broadcast = await startBroadcast(ROOM, microphone, (state) => states.push(state));
  await broadcast.stop();
  const room = control.rooms[0]!;
  expect(room.disconnectedWith).toBe(false);
  room.emit("disconnected");
  expect(states).toEqual(["connecting", "live"]); // no "disconnected" after a deliberate stop
});

test.each([
  ["connecting", "connectFailure"],
  ["publishing", "publishFailure"],
] as const)("a failure while %s leaves the room and is passed on", async (_case, failure) => {
  control[failure] = new Error("no route");
  await expect(startBroadcast(ROOM, microphone, () => undefined)).rejects.toThrow("no route");
  expect(control.rooms[0]!.disconnectedWith).toBe(false);
  expect(control.rooms[0]!.handlers.size).toBe(0);
});
