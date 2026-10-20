import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import LiveControls from "@/components/LiveControls";
import type { BroadcastPhase, BroadcastValue } from "@/hooks/useBroadcast";

function broadcast(phase: BroadcastPhase, error: string | null = null): BroadcastValue {
  return { phase, error, stream: null, start: jest.fn(), resume: jest.fn(), end: jest.fn(async () => undefined) };
}

function renderControls(value: BroadcastValue, canStart = true, onStart = jest.fn(), onResume = jest.fn()) {
  return render(<LiveControls broadcast={value} canStart={canStart} onStart={onStart} onResume={onResume} />);
}

test.each([
  ["idle", "Off air", ["Go live"]],
  ["starting", "Going live…", ["Go live"]],
  ["connecting", "Connecting your audio…", ["Go live"]],
  ["live", "Live: listeners can hear you", ["End stream"]],
  ["reconnecting", "Connection lost, reconnecting…", ["End stream"]],
  [
    "interrupted",
    "You're still live, but your audio isn't reaching listeners. Resume, or end the stream.",
    ["Resume", "End stream"],
  ],
  ["ending", "Ending…", ["Go live"]],
] as const)("%s says so and offers the right buttons", (phase, status, buttons) => {
  renderControls(broadcast(phase));
  expect(screen.getByRole("status")).toHaveTextContent(status);
  expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(buttons);
});

test.each([
  ["ready", "idle", true, true],
  ["missing a game or mic", "idle", false, false],
  ["already starting", "starting", true, false],
] as const)("go live is enabled only when %s", (_case, phase, canStart, isEnabled) => {
  renderControls(broadcast(phase), canStart);
  const button = screen.getByRole("button", { name: "Go live" });
  expect((button as HTMLButtonElement).disabled).toBe(!isEnabled);
});

test("resume needs a microphone", () => {
  renderControls(broadcast("interrupted"), false);
  expect(screen.getByRole("button", { name: "Resume" })).toBeDisabled();
});

test("the buttons start, resume and end", async () => {
  const onStart = jest.fn();
  const onResume = jest.fn();
  const { unmount } = renderControls(broadcast("idle"), true, onStart, onResume);
  await userEvent.click(screen.getByRole("button", { name: "Go live" }));
  expect(onStart).toHaveBeenCalled();
  unmount();
  const interrupted = broadcast("interrupted");
  renderControls(interrupted, true, onStart, onResume);
  await userEvent.click(screen.getByRole("button", { name: "Resume" }));
  expect(onResume).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  expect(interrupted.end).toHaveBeenCalled();
});

test("shows an error", () => {
  renderControls(broadcast("idle", "This event is over"));
  expect(screen.getByRole("alert")).toHaveTextContent("This event is over");
});
