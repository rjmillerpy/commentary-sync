"use client";

/** Choose a microphone and watch it move before going live. */

import type { MicrophoneValue } from "@/hooks/useMicrophone";

const LEVEL_STEPS = 100;
const DEFAULT_DEVICE = "";

interface Props {
  microphone: MicrophoneValue;
  isLocked: boolean;
}

export default function MicCheck({ microphone, isLocked }: Props) {
  const { devices, deviceId, level, error, choose } = microphone;
  const percent = Math.round(level * LEVEL_STEPS);
  return (
    <section className="card" aria-labelledby="mic-title">
      <h2 id="mic-title">2. Check your mic</h2>
      {error !== null && <p role="alert">{error}</p>}
      <label>
        Microphone
        <select
          value={deviceId ?? DEFAULT_DEVICE}
          disabled={isLocked || devices.length === 0}
          onChange={(event) => choose(event.target.value === DEFAULT_DEVICE ? null : event.target.value)}
        >
          <option value={DEFAULT_DEVICE}>Browser default</option>
          {devices.map((device, index) => (
            <option key={device.deviceId} value={device.deviceId}>
              {device.label || `Microphone ${index + 1}`}
            </option>
          ))}
        </select>
      </label>
      <label>
        Level
        <meter min={0} max={LEVEL_STEPS} value={percent} aria-valuetext={`${percent}%`} />
      </label>
      <p className="hint">Talk at your normal volume: the bar should move well past halfway.</p>
    </section>
  );
}
