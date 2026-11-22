/** Fine-tune (UI rule 1.4): the listener's own nudge on top of the
 * synced delay, a tenth of a second at a time, up to 10 s either way. For
 * what only their ears can tell: Bluetooth headphones, a TV that processes
 * its picture. Applied at once, and remembered on this phone. */

import { Stepper } from "@/components/Stepper";
import { clampFineTune, FINE_TUNE_STEP_SECONDS, formatOffset, MAX_FINE_TUNE_SECONDS } from "@/lib/delay";

interface FineTuneProps {
  value: number;
  onChange(seconds: number): void;
}

export function FineTune({ value, onChange }: FineTuneProps) {
  const nudge = (by: number) => onChange(clampFineTune(value + by));
  return (
    <Stepper
      title="Commentary early or late?"
      value={formatOffset(value)}
      valueLabel={`Fine-tune ${formatOffset(value)}`}
      down={{
        label: "Earlier",
        accessibilityLabel: "Hear the commentary a tenth of a second earlier",
        onPress: () => nudge(-FINE_TUNE_STEP_SECONDS),
        disabled: value <= -MAX_FINE_TUNE_SECONDS,
      }}
      up={{
        label: "Later",
        accessibilityLabel: "Hear the commentary a tenth of a second later",
        onPress: () => nudge(FINE_TUNE_STEP_SECONDS),
        disabled: value >= MAX_FINE_TUNE_SECONDS,
      }}
      hint="Hear a call before you see the play? Tap Later. After it? Tap Earlier."
    />
  );
}
