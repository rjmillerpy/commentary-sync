/** The commentary's volume and its own mute (UI rule 4). The TV's sound
 * is the TV remote's. */

import { StyleSheet, View } from "react-native";

import { StepButton, Stepper } from "@/components/Stepper";
import { clampVolume, VOLUME_STEP, VOLUME_STEPS } from "@/lib/volume";
import { SPACE } from "@/theme";

interface VolumeControlProps {
  volume: number;
  onVolume(volume: number): void;
  isMuted: boolean;
  onMute(muted: boolean): void;
}

export function VolumeControl({ volume, onVolume, isMuted, onMute }: VolumeControlProps) {
  const level = Math.round(volume * VOLUME_STEPS);
  return (
    <View style={styles.volume}>
      <Stepper
        title="Commentary volume"
        value={isMuted ? "Muted" : `${level} of ${VOLUME_STEPS}`}
        valueLabel={isMuted ? "Commentary muted" : `Commentary volume ${level} of ${VOLUME_STEPS}`}
        down={{ label: "−", accessibilityLabel: "Quieter", onPress: () => onVolume(clampVolume(volume - VOLUME_STEP)), disabled: volume <= 0 }}
        up={{ label: "+", accessibilityLabel: "Louder", onPress: () => onVolume(clampVolume(volume + VOLUME_STEP)), disabled: volume >= 1 }}
      />
      <StepButton label={isMuted ? "Unmute commentary" : "Mute commentary"} onPress={() => onMute(!isMuted)} />
    </View>
  );
}

const styles = StyleSheet.create({
  volume: { gap: SPACE.sm },
});
