import { render, screen } from "@testing-library/react";

import ListenerHealth from "@/components/ListenerHealth";
import { SYNC_HEALTH } from "../_fakeApi";

test("how many listen, how many are in sync, and how late they hear the commentator", () => {
  render(<ListenerHealth listeners={12} health={SYNC_HEALTH} />);
  expect(screen.getByText("Listening").nextSibling).toHaveTextContent("12");
  expect(screen.getByText("In sync with their TV").nextSibling).toHaveTextContent("9 of 11");
  expect(screen.getByText("They hear you").nextSibling).toHaveTextContent("about 23 s late");
  expect(screen.getByText(/2 listeners' TVs don't sound like yours: they may be on another channel/)).toBeInTheDocument();
});

test("one not heard reads as one", () => {
  render(<ListenerHealth listeners={1} health={{ in_sync: 0, not_heard: 1, typical_delay_seconds: null }} />);
  expect(screen.getByText(/^1 listener's TV doesn't sound like yours/)).toBeInTheDocument();
});

test("before anyone syncs, it says so; with nothing known yet, it waits", () => {
  const { rerender } = render(<ListenerHealth listeners={3} health={{ in_sync: 0, not_heard: 0, typical_delay_seconds: null }} />);
  expect(screen.getByText("In sync with their TV").nextSibling).toHaveTextContent("No one yet");
  expect(screen.queryByText(/sound like yours/)).toBeNull();
  rerender(<ListenerHealth listeners={null} health={null} />);
  expect(screen.getByText("Listening").nextSibling).toHaveTextContent("…");
  expect(screen.getByText("They hear you").nextSibling).toHaveTextContent("…");
});
