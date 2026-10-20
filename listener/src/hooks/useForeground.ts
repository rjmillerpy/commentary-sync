/** When the app last came back to the front (ms since the epoch), or null:
 * the listener may have paused the TV while away. */

import { useEffect, useState } from "react";
import { AppState } from "react-native";

export function useForeground(): number | null {
  const [foregroundedAt, setForegroundedAt] = useState<number | null>(null);

  useEffect(() => {
    let previous: string | null | undefined = AppState.currentState;
    const subscription = AppState.addEventListener("change", (next) => {
      if (next === "active" && previous !== "active") setForegroundedAt(Date.now());
      previous = next;
    });
    return () => subscription.remove();
  }, []);

  return foregroundedAt;
}
