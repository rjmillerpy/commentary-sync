import { readFileSync } from "fs";
import { join } from "path";

import { GATE_MODULE_URL, GATE_TIMING, type GateLevels, type GateReport, type GateTiming, openGate, SILENCE_DB, toDecibels, toPower } from "@/lib/gate";
import { type FakeMedia, FakeStream, installMedia } from "../_fakeMedia";

interface GateCore {
  setThresholdPower(power: number): void;
  process(input: Float32Array, output: Float32Array): GateReport | null;
}

interface WorkletProcessor {
  port: { onmessage: ((event: { data: unknown }) => void) | null };
  process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean;
}

/** Runs the served file (public/voice-gate.js) as the audio thread would,
 * with that scope's globals stubbed. */
function loadWorklet() {
  const source = readFileSync(join(__dirname, "../../public", GATE_MODULE_URL), "utf8");
  const registered: Record<string, new (options: AudioWorkletNodeOptions) => WorkletProcessor> = {};
  const posted: unknown[] = [];
  class AudioWorkletProcessor {
    readonly port = {
      onmessage: null as ((event: { data: unknown }) => void) | null,
      postMessage: (message: unknown) => posted.push(message),
    };
  }
  const register = (name: string, processor: never) => (registered[name] = processor);
  const run = new Function("AudioWorkletProcessor", "registerProcessor", "sampleRate", `${source}\nreturn createGateCore;`);
  const createGateCore = run(AudioWorkletProcessor, register, RATE) as (rate: number, timing: GateTiming) => GateCore;
  return { createGateCore, registered, posted };
}

// A slow sample rate keeps the arithmetic readable: 1 000 samples a second.
const RATE = 1_000;
const LOOKAHEAD = Math.round(GATE_TIMING.lookaheadSeconds * RATE);
const LOUD = 0.5;
const SOFT = 0.01;

/** Gates `samples` through `core`; returns the output and every report. */
function run(core: GateCore, samples: Float32Array): { output: Float32Array; reports: GateReport[] } {
  const output = new Float32Array(samples.length);
  const reports: GateReport[] = [];
  const block = 10;
  for (let start = 0; start < samples.length; start += block) {
    const report = core.process(samples.subarray(start, start + block), output.subarray(start, start + block));
    if (report !== null) reports.push(report);
  }
  return { output, reports };
}

const steady = (amplitude: number, seconds: number) => new Float32Array(seconds * RATE).fill(amplitude);
function then(...parts: Float32Array[]): Float32Array {
  const joined = new Float32Array(parts.reduce((total, part) => total + part.length, 0));
  parts.reduce((offset, part) => (joined.set(part, offset), offset + part.length), 0);
  return joined;
}

const { createGateCore } = loadWorklet();

function thresholdCore(decibels: number): GateCore {
  const core = createGateCore(RATE, GATE_TIMING);
  core.setThresholdPower(toPower(decibels));
  return core;
}

test("until the TV check sets a threshold, nothing gets through", () => {
  const { output } = run(createGateCore(RATE, GATE_TIMING), steady(LOUD, 1));
  expect(output.every((sample) => sample === 0)).toBe(true);
});

test("sound below the threshold is silenced", () => {
  const { output } = run(thresholdCore(-20), steady(SOFT, 1));
  expect(output.every((sample) => sample === 0)).toBe(true);
});

test("a voice above the threshold goes through, delayed by the look-ahead", () => {
  const { output } = run(thresholdCore(-20), steady(LOUD, 1));
  expect(output.subarray(0, LOOKAHEAD).every((sample) => sample === 0)).toBe(true);
  expect(output[500]).toBeCloseTo(LOUD);
});

test("the gate holds open between words, then closes", () => {
  const word = steady(LOUD, 1);
  const { output } = run(thresholdCore(-20), then(word, steady(SOFT, 1)));
  const afterWord = 1_000 + LOOKAHEAD;
  expect(output[afterWord + 100]).toBeCloseTo(SOFT); // a short pause: still open
  expect(output[1_999]).toBe(0); // the hold and the release are over
});

test("every report gives the microphone's power before the gate, and how much got through", () => {
  const { reports } = run(thresholdCore(-20), then(steady(SOFT, 0.5), steady(LOUD, 0.5)));
  expect(reports).toHaveLength(1 / GATE_TIMING.reportSeconds);
  expect(reports[0]).toEqual({ power: expect.closeTo(SOFT * SOFT, 6), openShare: 0 });
  expect(reports.at(-1)).toEqual({ power: expect.closeTo(LOUD * LOUD, 6), openShare: 1 });
});

test("the processor gates the microphone, reports, and takes thresholds from the page", () => {
  const { registered, posted } = loadWorklet();
  const gate = new registered["voice-gate"]!({ processorOptions: GATE_TIMING });
  gate.port.onmessage!({ data: toPower(-20) });
  const output = new Float32Array(50);
  for (let block = 0; block < 2; block += 1) expect(gate.process([[steady(LOUD, 0.05)]], [[output]])).toBe(true);
  expect(output.at(-1)).toBeCloseTo(LOUD);
  expect(posted).toHaveLength(2);
  const silent = new Float32Array(50).fill(1);
  expect(gate.process([[]], [[silent]])).toBe(true); // no input: a disconnected microphone
  expect(silent.every((sample) => sample === 0)).toBe(true);
});

test.each([
  ["full scale", 1, 0],
  ["a tenth of the power", 0.1, -10],
  ["silence", 0, SILENCE_DB],
  ["below the floor", 1e-20, SILENCE_DB],
])("power in decibels: %s", (_case, power, decibels) => {
  expect(toDecibels(power)).toBeCloseTo(decibels);
});

test("decibels back to power", () => {
  expect(toPower(-20)).toBeCloseTo(0.01);
});

describe("openGate", () => {
  let media: FakeMedia;

  beforeEach(() => {
    media = installMedia();
  });

  test("puts the gate's output on air, sets thresholds, reports levels, and closes", async () => {
    const heard: GateLevels[] = [];
    const gate = await openGate(new FakeStream("default") as unknown as MediaStream, (levels) => heard.push(levels));
    const node = media.worklets[0]!;
    expect(media.contexts[0]!.audioWorklet.addModule).toHaveBeenCalledWith("/voice-gate.js");
    expect(node.name).toBe("voice-gate");
    expect(node.options).toMatchObject({ outputChannelCount: [1], processorOptions: GATE_TIMING });
    expect(gate.track).toBe(media.destinations[0]!.track);

    gate.setThreshold(-30);
    expect(node.posted[0]).toBeCloseTo(0.001);
    node.post({ power: 0.01, openShare: 0.5 });
    expect(heard).toEqual([{ levelDb: expect.closeTo(-20, 6), openShare: 0.5 }]);

    gate.close();
    expect(media.contexts[0]!.closed).toBe(true);
    expect(gate.track.stop).toHaveBeenCalled();
    node.post({ power: 0.01, openShare: 0.5 });
    expect(heard).toHaveLength(1); // nothing after closing
  });

  test("a browser without AudioWorklet is an error, and nothing is left open", async () => {
    media.workletFailure = "NotSupportedError";
    await expect(openGate(new FakeStream("default") as unknown as MediaStream, jest.fn())).rejects.toMatchObject({
      name: "NotSupportedError",
    });
    expect(media.contexts[0]!.closed).toBe(true);
  });
});
