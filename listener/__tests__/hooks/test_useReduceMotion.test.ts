import { act, renderHook, waitFor } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";

import { useReduceMotion } from "@/hooks/useReduceMotion";

afterEach(() => jest.restoreAllMocks());

test("follows the phone's reduce-motion setting, and its changes", async () => {
  let changed: (reduced: boolean) => void = () => undefined;
  const remove = jest.fn();
  jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);
  jest.spyOn(AccessibilityInfo, "addEventListener").mockImplementation((_event, listener) => {
    changed = listener as (reduced: boolean) => void;
    return { remove } as unknown as ReturnType<typeof AccessibilityInfo.addEventListener>;
  });
  const { result, unmount } = await renderHook(useReduceMotion);
  await waitFor(() => expect(result.current).toBe(true));
  await act(() => changed(false));
  expect(result.current).toBe(false);
  await unmount();
  expect(remove).toHaveBeenCalled();
});
