import { fireEvent, render, screen } from "@testing-library/react-native";

import { PauseButton } from "@/components/PauseButton";

test.each([
  [false, "Pause commentary"],
  [true, "Play commentary"],
])("paused %s: %s", async (isPaused, label) => {
  const onPress = jest.fn();
  await render(<PauseButton isPaused={isPaused} onPress={onPress} />);
  await fireEvent.press(screen.getByRole("button", { name: label }));
  expect(onPress).toHaveBeenCalled();
});
