import { fireEvent, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import { Screen } from "@/components/Screen";

test("shows its title as a header, the line under it, and its content", async () => {
  await render(
    <Screen title="Games" subtitle="Pick the game on your TV">
      <Text>content</Text>
    </Screen>,
  );
  expect(screen.getByRole("header", { name: "Games" })).toBeOnTheScreen();
  expect(screen.getByText("Pick the game on your TV")).toBeOnTheScreen();
  expect(screen.getByText("content")).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
});

test("back and the header action are buttons", async () => {
  const onBack = jest.fn();
  const onRefresh = jest.fn();
  await render(<Screen title="T" onBack={onBack} action={{ label: "Refresh", onPress: onRefresh }} scrolls={false}>{null}</Screen>);
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  await fireEvent.press(screen.getByRole("button", { name: "Refresh" }));
  expect([onBack.mock.calls.length, onRefresh.mock.calls.length]).toEqual([1, 1]);
});
