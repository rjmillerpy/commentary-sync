import { CHUNK_SECONDS, Chunker, recordRoom, REFERENCE_SAMPLE_RATE, type ReferenceChunk, toPcm } from "@/lib/reference";
import { type FakeMedia, FakeStream, installMedia } from "../_fakeMedia";

let media: FakeMedia;

beforeEach(() => {
  media = installMedia();
});

test("blocks are gathered into chunks, each stamped with its first sample's time", () => {
  const chunks: ReferenceChunk[] = [];
  const chunker = new Chunker(4, 2, (chunk) => chunks.push(chunk)); // 2 samples a second, 2 s chunks
  chunker.add(new Float32Array([0.1, 0.2, 0.3]), 100);
  chunker.add(new Float32Array([0.4, 0.5, 0.6]), 101.5);
  expect(chunks).toHaveLength(1);
  expect(chunks[0]!.capturedAt).toBe(100);
  chunker.add(new Float32Array([0.7, 0.8]), 103);
  expect(chunks.map((chunk) => chunk.capturedAt)).toEqual([100, 102]);
  expect(Array.from(chunks[1]!.pcm)).toEqual(Array.from(toPcm(new Float32Array([0.5, 0.6, 0.7, 0.8]))));
});

test.each([
  ["silence", 0, 0],
  ["full scale", 1, 32767],
  ["full negative", -1, -32767],
  ["clipping above", 1.5, 32767],
  ["clipping below", -2, -32767],
])("samples become 16-bit PCM: %s", (_case, sample, expected) => {
  expect(toPcm(new Float32Array([sample]))[0]).toBe(expected);
});

test("the room is recorded at 8 kHz in 5 s chunks, stamped in device time", async () => {
  const chunks: ReferenceChunk[] = [];
  const stop = await recordRoom(new FakeStream("default") as unknown as MediaStream, (chunk) => chunks.push(chunk));
  expect(media.contexts[0]!.sampleRate).toBe(REFERENCE_SAMPLE_RATE);
  const worklet = media.worklets[0]!;
  expect(worklet.options).toMatchObject({ numberOfOutputs: 0 });
  const chunkSamples = CHUNK_SECONDS * REFERENCE_SAMPLE_RATE;
  worklet.deliver(16_000, new Float32Array(chunkSamples)); // starts 2 s into the context
  expect(chunks).toHaveLength(1);
  expect(chunks[0]!.pcm).toHaveLength(chunkSamples);
  expect(chunks[0]!.capturedAt).toBeCloseTo(media.contexts[0]!.startedAt + 2);
  stop();
  expect(media.contexts[0]!.closed).toBe(true);
  worklet.deliver(0, new Float32Array(chunkSamples));
  expect(chunks).toHaveLength(1); // nothing after stopping
});

test("a browser that refuses the worklet is an error for the caller", async () => {
  media.workletFailure = "NotSupportedError";
  await expect(recordRoom(new FakeStream("default") as unknown as MediaStream, jest.fn())).rejects.toMatchObject({
    name: "NotSupportedError",
  });
  expect(URL.revokeObjectURL).toHaveBeenCalled();
});
