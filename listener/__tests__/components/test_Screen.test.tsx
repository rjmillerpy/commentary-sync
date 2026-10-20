import { fireEvent, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import { Screen } from "@/components/Screen";

test("shows its title as a header, and its content", async () => {
  await render(
    <Screen title="Games">
      <Text>content</Text>
    </Screen>,
  );
  expect(screen.getByRole("header", { name: "Games" })).toBeOnTheScreen();
  expect(screen.getByText("content")).toBeOnTheScreen();
  expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
});

test("back and the header action are buttons", async () => {
  const onBack = jest.fn();
  const onSignOut = jest.fn();
  await render(<Screen title="T" onBack={onBack} action={{ label: "Sign out", onPress: onSignOut }}>{null}</Screen>);
  await fireEvent.press(screen.getByRole("button", { name: "Back" }));
  await fireEvent.press(screen.getByRole("button", { name: "Sign out" }));
  expect([onBack.mock.calls.length, onSignOut.mock.calls.length]).toEqual([1, 1]);
});
