import { fireEvent, render, screen } from "@testing-library/react-native";

import { FineTune } from "@/components/FineTune";

test.each([
  ["Hear the commentary a tenth of a second earlier", 0.1],
  ["Hear the commentary a tenth of a second later", 0.3],
])("%s", async (button, expected) => {
  const onChange = jest.fn();
  await render(<FineTune value={0.2} onChange={onChange} />);
  await fireEvent.press(screen.getByRole("button", { name: button }));
  expect(onChange).toHaveBeenCalledWith(expected);
});

test("shows the offset with its sign, and which way to go", async () => {
  await render(<FineTune value={-1.2} onChange={jest.fn()} />);
  expect(screen.getByLabelText("Fine-tune −1.2 s")).toBeOnTheScreen();
  expect(screen.getByText(/before you see the play\? Tap Later/)).toBeOnTheScreen();
});

test.each([
  [10, "Hear the commentary a tenth of a second later"],
  [-10, "Hear the commentary a tenth of a second earlier"],
])("at %s s it goes no further that way", async (value, button) => {
  await render(<FineTune value={value} onChange={jest.fn()} />);
  expect(screen.getByRole("button", { name: button })).toBeDisabled();
});
