import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EndStream from "@/components/EndStream";

test("asks once, in place, saying who it cuts off, then ends", async () => {
  const onEnd = jest.fn();
  render(<EndStream listeners={12} onEnd={onEnd} />);
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  expect(screen.getByRole("group", { name: "End the stream?" })).toHaveTextContent("End the stream for 12 listeners?");
  expect(onEnd).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Yes, end it" }));
  expect(onEnd).toHaveBeenCalled();
});

test("Keep going changes nothing", async () => {
  const onEnd = jest.fn();
  render(<EndStream listeners={1} onEnd={onEnd} />);
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  expect(screen.getByText("End the stream for 1 listener?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Keep going" }));
  expect(screen.getByRole("button", { name: "End stream" })).toBeInTheDocument();
  expect(onEnd).not.toHaveBeenCalled();
});

test.each([null, 0])("with %s listeners it just says the stream", async (listeners) => {
  render(<EndStream listeners={listeners} onEnd={jest.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  expect(screen.getByText("End the stream?")).toBeInTheDocument();
});
