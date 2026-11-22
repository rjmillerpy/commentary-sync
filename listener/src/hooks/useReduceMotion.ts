/** Whether the listener asked the phone to reduce motion (UI rule 10):
 * then nothing in the app animates. */

import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

export function useReduceMotion(): boolean {
  const [isReduced, setIsReduced] = useState(false);
  useEffect(() => {
    let isCurrent = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((reduced) => {
      if (isCurrent) setIsReduced(reduced);
    });
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", setIsReduced);
    return () => {
      isCurrent = false;
      subscription.remove();
    };
  }, []);
  return isReduced;
}
