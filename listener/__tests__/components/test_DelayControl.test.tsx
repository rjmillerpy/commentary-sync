import { fireEvent, render, screen } from "@testing-library/react-native";

import { DelayControl } from "@/components/DelayControl";

test.each([
  ["Less delay, 5 seconds", 7.5],
  ["Less delay, 0.5 seconds", 12],
  ["More delay, 0.5 seconds", 13],
  ["More delay, 5 seconds", 17.5],
])("%s", async (button, expected) => {
  const onChange = jest.fn();
  await render(<DelayControl delay={12.5} onChange={onChange} />);
  await fireEvent.press(screen.getByRole("button", { name: button }));
  expect(onChange).toHaveBeenCalledWith(expected);
});

test("shows the delay and how to pick it", async () => {
  await render(<DelayControl delay={12.5} onChange={jest.fn()} />);
  expect(screen.getByLabelText("Delay 12.5 s")).toBeOnTheScreen();
  expect(screen.getByText(/until the commentary matches your TV/)).toBeOnTheScreen();
});

test("the delay can't go below zero", async () => {
  const onChange = jest.fn();
  await render(<DelayControl delay={2} onChange={onChange} />);
  await fireEvent.press(screen.getByRole("button", { name: "Less delay, 5 seconds" }));
  expect(onChange).toHaveBeenCalledWith(0);
});
