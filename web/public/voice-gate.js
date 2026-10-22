/* The voice gate's audio-thread half: src/lib/gate.ts explains the gate and
 * loads this file. It is served as is, never bundled, so the browser runs
 * exactly this source; __tests__/lib/test_gate.test.ts runs it too. Its
 * settings arrive from the page (processorOptions), and thresholds and
 * reports are in power (mean square), so it holds no numbers of its own. */

/** The gate: `process` gates one block into `output` and returns a report
 * ({ power, openShare }) when a report period ends, else null. */
function createGateCore(sampleRate, timing) {
  const smoothing = 1 - Math.exp(-1 / Math.max(1, timing.smoothingSeconds * sampleRate));
  const holdSamples = Math.round(timing.holdSeconds * sampleRate);
  const attackStep = 1 / Math.max(1, timing.attackSeconds * sampleRate);
  const releaseStep = 1 / Math.max(1, timing.releaseSeconds * sampleRate);
  const delayed = new Float32Array(Math.max(1, Math.round(timing.lookaheadSeconds * sampleRate)));
  const reportSamples = Math.max(1, Math.round(timing.reportSeconds * sampleRate));
  let thresholdPower = Infinity; // closed until the TV check sets a threshold
  let envelope = 0;
  let quietFor = holdSamples;
  let gain = 0;
  let cursor = 0;
  let period = { power: 0, open: 0, samples: 0 };

  function gateOne(sample) {
    envelope += (sample * sample - envelope) * smoothing;
    quietFor = envelope >= thresholdPower ? 0 : Math.min(quietFor + 1, holdSamples);
    gain = quietFor < holdSamples ? Math.min(1, gain + attackStep) : Math.max(0, gain - releaseStep);
    const out = delayed[cursor] * gain; // the look-ahead: the sample from that long ago
    delayed[cursor] = sample;
    cursor = (cursor + 1) % delayed.length;
    return out;
  }

  function measure(sample) {
    period = { power: period.power + sample * sample, open: period.open + (gain > 0 ? 1 : 0), samples: period.samples + 1 };
    if (period.samples < reportSamples) return null;
    const report = { power: period.power / period.samples, openShare: period.open / period.samples };
    period = { power: 0, open: 0, samples: 0 };
    return report;
  }

  return {
    setThresholdPower(power) {
      thresholdPower = power;
    },
    process(input, output) {
      let report = null;
      for (let index = 0; index < input.length; index += 1) {
        output[index] = gateOne(input[index]);
        report = measure(input[index]) ?? report;
      }
      return report;
    },
  };
}

class VoiceGate extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.core = createGateCore(sampleRate, options.processorOptions);
    this.port.onmessage = (event) => this.core.setThresholdPower(event.data);
  }

  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    const output = outputs[0][0];
    if (!input) {
      output.fill(0); // no microphone connected: silence
      return true;
    }
    const report = this.core.process(input, output);
    if (report !== null) this.port.postMessage(report);
    return true;
  }
}

registerProcessor("voice-gate", VoiceGate);
