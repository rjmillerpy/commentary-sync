import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import GoLive from "@/components/GoLive";

test("ready: says so, and Go live goes live", async () => {
  const onStart = jest.fn();
  render(<GoLive phase="idle" missing={null} error={null} onStart={onStart} />);
  expect(screen.getByRole("status")).toHaveTextContent("Ready.");
  await userEvent.click(screen.getByRole("button", { name: "Go live" }));
  expect(onStart).toHaveBeenCalled();
});

test("something missing: says what, and can't go live yet", () => {
  render(<GoLive phase="idle" missing="Pick the game you're watching first." error={null} onStart={jest.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("Pick the game you're watching first.");
  expect(screen.getByRole("button", { name: "Go live" })).toBeDisabled();
});

test("going live: says so, once", () => {
  render(<GoLive phase="starting" missing={null} error={null} onStart={jest.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("Going live…");
  expect(screen.getByRole("button", { name: "Go live" })).toBeDisabled();
});

test("a failure to go live is shown", () => {
  render(<GoLive phase="idle" missing={null} error="Couldn't connect your audio." onStart={jest.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't connect your audio.");
});
