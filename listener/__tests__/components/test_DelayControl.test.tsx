import { fireEvent, render, screen } from "@testing-library/react-native";

import { DelayControl } from "@/components/DelayControl";

test.each([
  ["Less delay, 5 seconds", 7.5],
  ["Less delay, 1 second", 11.5],
  ["More delay, 1 second", 13.5],
  ["More delay, 5 seconds", 17.5],
])("%s", async (button, expected) => {
  const onChange = jest.fn();
  await render(<DelayControl delay={12.5} onChange={onChange} />);
  await fireEvent.press(screen.getByRole("button", { name: button }));
  expect(onChange).toHaveBeenCalledWith(expected);
});

test("shows the delay and which way to move it", async () => {
  await render(<DelayControl delay={12.5} onChange={jest.fn()} />);
  expect(screen.getByLabelText("Delay 12.5 s")).toBeOnTheScreen();
  expect(screen.getByText(/ahead of your TV\? More delay/)).toBeOnTheScreen();
});

test("the delay can't go below zero", async () => {
  const onChange = jest.fn();
  await render(<DelayControl delay={2} onChange={onChange} />);
  await fireEvent.press(screen.getByRole("button", { name: "Less delay, 5 seconds" }));
  expect(onChange).toHaveBeenCalledWith(0);
});
