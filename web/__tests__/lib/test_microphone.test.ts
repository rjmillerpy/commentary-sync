import {
  closeMicrophone,
  levelOf,
  listMicrophones,
  MICROPHONE_CONSTRAINTS,
  microphoneFailure,
  openMicrophone,
  watchLevel,
} from "@/lib/microphone";
import { type FakeMedia, installMedia } from "../_fakeMedia";

let media: FakeMedia;

beforeEach(() => {
  media = installMedia();
});

test("the default microphone opens with speech cleanup on", async () => {
  await openMicrophone(null);
  expect(media.constraints[0]).toEqual({ audio: MICROPHONE_CONSTRAINTS, video: false });
  expect(MICROPHONE_CONSTRAINTS).toMatchObject({ echoCancellation: true, noiseSuppression: true });
});

test("a chosen microphone is asked for exactly", async () => {
  await openMicrophone("usb-mic");
  expect(media.constraints[0]!.audio).toMatchObject({ deviceId: { exact: "usb-mic" } });
});

test("only inputs are listed", async () => {
  expect((await listMicrophones()).map((device) => device.deviceId)).toEqual(["default", "usb-mic"]);
});

test("closing stops every track", async () => {
  const stream = await openMicrophone(null);
  closeMicrophone(stream);
  expect(media.opened[0]!.track.stop).toHaveBeenCalled();
});

test.each([
  ["NotAllowedError", "Microphone access is blocked. Allow it in the browser's site settings."],
  ["NotFoundError", "No microphone found. Plug one in and try again."],
  ["NotReadableError", "The microphone is in use by another app."],
  ["AbortError", "Couldn't open the microphone."],
])("a %s is explained", (name, message) => {
  expect(microphoneFailure(new DOMException("x", name))).toBe(message);
});

test("regression: a page without a secure connection gets an explanation, not a crash", async () => {
  // Found by the e2e tests: on plain http (other than localhost) browsers
  // leave navigator.mediaDevices out, and opening the mic threw synchronously,
  // past the studio's catch, taking the whole page down.
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
  const opening = openMicrophone(null);
  await expect(opening).rejects.toMatchObject({ name: "InsecureContextError" });
  await expect(listMicrophones()).rejects.toMatchObject({ name: "InsecureContextError" });
  expect(microphoneFailure(await opening.catch((error: unknown) => error))).toBe(
    "The microphone only works over a secure (https) connection.",
  );
});

test("something that isn't an error is still explained", () => {
  expect(microphoneFailure("nope")).toBe("Couldn't open the microphone.");
});

test.each([
  ["silence", 128, 0],
  ["a quiet signal", 134, (6 / 128) * 4],
  ["a loud signal", 255, 1],
])("the level of %s", (_case, byte, expected) => {
  expect(levelOf(new Uint8Array(64).fill(byte))).toBeCloseTo(expected);
});

test("no samples is silence", () => {
  expect(levelOf(new Uint8Array(0))).toBe(0);
});

test("the level is reported every 100 ms until stopped, then the context closes", async () => {
  jest.useFakeTimers();
  const stream = await openMicrophone(null);
  const levels: number[] = [];
  media.sampleByte = 255;
  const stop = watchLevel(stream, (level) => levels.push(level));
  jest.advanceTimersByTime(300);
  stop();
  jest.advanceTimersByTime(300);
  expect(levels).toEqual([1, 1, 1]);
  expect(media.contexts[0]!.closed).toBe(true);
  jest.useRealTimers();
});
