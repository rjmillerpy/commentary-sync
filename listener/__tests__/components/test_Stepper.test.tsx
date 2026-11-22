import { fireEvent, render, screen } from "@testing-library/react-native";

import { Stepper } from "@/components/Stepper";

test("a value between two labelled steps", async () => {
  const down = jest.fn();
  const up = jest.fn();
  await render(
    <Stepper
      title="Volume"
      value="5 of 10"
      valueLabel="Volume 5 of 10"
      down={{ label: "−", accessibilityLabel: "Quieter", onPress: down }}
      up={{ label: "+", onPress: up, disabled: true }}
      hint="A hint"
    />,
  );
  expect(screen.getByLabelText("Volume 5 of 10")).toBeOnTheScreen();
  expect(screen.getByText("A hint")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Quieter" }));
  await fireEvent.press(screen.getByRole("button", { name: "+" }));
  expect([down.mock.calls.length, up.mock.calls.length]).toEqual([1, 0]);
  expect(screen.getByRole("button", { name: "+" })).toBeDisabled();
});
