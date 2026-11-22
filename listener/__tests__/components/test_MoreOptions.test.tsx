import { fireEvent, render, screen } from "@testing-library/react-native";

import { MoreOptions } from "@/components/MoreOptions";

const props = (overrides = {}) => ({ isSyncOn: true, onSyncOn: jest.fn(), baseDelay: 12.3, onBaseDelay: jest.fn(), fineTune: 0.2, behind: 12.4, ...overrides });

test("folded away until asked for, then shows the sync details", async () => {
  await render(<MoreOptions {...props()} />);
  expect(screen.queryByText("Sync details")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "More options" }));
  expect(screen.getByText("Delay: 12.3 s (from your TV)")).toBeOnTheScreen();
  expect(screen.getByText("Fine-tune: +0.2 s")).toBeOnTheScreen();
  expect(screen.getByText("Behind the commentator: 12.4 s")).toBeOnTheScreen();
  expect(screen.queryByLabelText("Delay 12.3 s")).toBeNull(); // no hand-set delay while syncing
  await fireEvent.press(screen.getByRole("button", { name: "Fewer options" }));
  expect(screen.queryByText("Sync details")).toBeNull();
});

test("turning sync off, and setting the delay by hand once it is", async () => {
  const value = props({ isSyncOn: false, behind: null });
  await render(<MoreOptions {...value} />);
  await fireEvent.press(screen.getByRole("button", { name: "More options" }));
  expect(screen.getByText("Delay: 12.3 s (set by you)")).toBeOnTheScreen();
  expect(screen.getByText("Behind the commentator: not known yet")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "More delay, 1 second" }));
  expect(value.onBaseDelay).toHaveBeenCalledWith(13.3);
  await fireEvent(screen.getByLabelText("Keep in sync with my TV"), "valueChange", true);
  expect(value.onSyncOn).toHaveBeenCalledWith(true);
});
