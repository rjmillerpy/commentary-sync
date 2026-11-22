import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import OnAir from "@/components/OnAir";
import type { BroadcastPhase, BroadcastValue } from "@/hooks/useBroadcast";
import { STREAM, SYNC_HEALTH } from "../_fakeApi";

function broadcast(phase: BroadcastPhase, error: string | null = null): BroadcastValue {
  return { phase, error, stream: STREAM as BroadcastValue["stream"], start: jest.fn(), resume: jest.fn(), end: jest.fn(async () => undefined) };
}

function renderOnAir(value: BroadcastValue, overrides: Partial<Parameters<typeof OnAir>[0]> = {}) {
  const onResume = jest.fn();
  render(
    <OnAir broadcast={value} gameTitle="Texans at Jaguars" listeners={12} health={SYNC_HEALTH} referenceStatus="on" canResume onResume={onResume} {...overrides} />,
  );
  return onResume;
}

test.each([
  ["connecting", "Connecting your audio…"],
  ["live", "Listeners can hear you"],
  ["reconnecting", "Connection lost, reconnecting…"],
  ["interrupted", "Your audio isn't reaching listeners. Resume, or end the stream."],
  ["ending", "Ending…"],
] as const)("%s says so", (phase, text) => {
  renderOnAir(broadcast(phase));
  expect(screen.getAllByRole("status")[0]).toHaveTextContent(text); // the connection; the sync note is another
});

test("live: the game, LIVE, how long, the listeners and their sync, and ending", async () => {
  const value = broadcast("live");
  renderOnAir(value);
  expect(screen.getByRole("heading", { name: "Texans at Jaguars" })).toBeInTheDocument();
  expect(screen.getByText("● LIVE")).toBeInTheDocument();
  expect(screen.getByText(/on air \d+:\d\d/)).toBeInTheDocument();
  expect(screen.getByText("9 of 11")).toBeInTheDocument();
  expect(screen.getByText(/Listeners can sync their TVs to yours/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Resume" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "End stream" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, end it" }));
  expect(value.end).toHaveBeenCalled();
});

test("interrupted: not live, and Resume brings the audio back", async () => {
  const onResume = renderOnAir(broadcast("interrupted"), { gameTitle: null });
  expect(screen.getByRole("heading", { name: "Your stream" })).toBeInTheDocument();
  expect(screen.getByText("○ NOT REACHING LISTENERS")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Resume" }));
  expect(onResume).toHaveBeenCalled();
});

test("ending: nothing left to press", () => {
  renderOnAir(broadcast("ending"));
  expect(screen.queryByRole("button")).toBeNull();
});

test("an error is shown", () => {
  renderOnAir(broadcast("interrupted", "This stream has already ended"));
  expect(screen.getByRole("alert")).toHaveTextContent("This stream has already ended");
});
