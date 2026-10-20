import { fireEvent, render, screen } from "@testing-library/react-native";

import { SyncPanel } from "@/components/SyncPanel";
import type { TvSyncState } from "@/hooks/useTvSync";

const AT = 1_792_400_000_000;

async function renderPanel(state: TvSyncState, overrides: Partial<Parameters<typeof SyncPanel>[0]> = {}) {
  const props = { state, onSync: jest.fn(), autoSync: true, onAutoSyncChange: jest.fn(), ...overrides };
  await render(<SyncPanel {...props} />);
  return props;
}

test.each<[string, TvSyncState, RegExp]>([
  ["idle", { kind: "idle" }, /hold the phone near it/],
  ["listening, asked for", { kind: "recording", auto: false }, /Listening to your TV for 10 seconds/],
  ["listening, automatic", { kind: "recording", auto: true }, /still in sync \(the commentary goes quiet for 6 s\)/],
  ["matching", { kind: "matching", auto: false }, /Matching it to the commentator's TV/],
  ["synced", { kind: "synced", auto: false, changed: true, at: AT, delay: 23.5, pauseTv: 0 }, /Synced: the commentary now runs 23.5 s behind/],
  ["ahead", { kind: "synced", auto: false, changed: true, at: AT, delay: 4, pauseTv: 6.5 }, /Pause your TV for 6.5 s, then play/],
  ["automatic, unchanged", { kind: "synced", auto: true, changed: false, at: AT, delay: 20, pauseTv: 0 }, /Checked: still in sync/],
  ["automatic, moved", { kind: "synced", auto: true, changed: true, at: AT, delay: 31, pauseTv: 0 }, /timing changed: the commentary now runs 31.0 s behind/],
  ["automatic, now ahead", { kind: "synced", auto: true, changed: true, at: AT, delay: 4, pauseTv: 2 }, /Pause your TV for 2.0 s/],
  ["not found, asked for", { kind: "not-found", auto: false, misses: 0 }, /Couldn't find your TV's sound/],
  ["automatic, missed repeatedly", { kind: "not-found", auto: true, misses: 3 }, /Auto-sync can't hear your TV/],
  ["failed", { kind: "failed", auto: false, detail: "Offline." }, /Offline\./],
])("%s", async (_case, state, text) => {
  await renderPanel(state);
  expect(screen.getByText(text)).toBeOnTheScreen();
});

test("an automatic check that misses once or twice says nothing", async () => {
  await renderPanel({ kind: "not-found", auto: true, misses: 2 });
  expect(screen.queryByText(/hear your TV|find your TV/)).toBeNull();
});

test("an automatic check's failure isn't shown as an alarm", async () => {
  await renderPanel({ kind: "failed", auto: true, detail: "Couldn't sync; try again." });
  expect(screen.queryByRole("alert")).toBeNull();
});

test("the button starts a sync, and is off while one runs", async () => {
  const props = await renderPanel({ kind: "idle" });
  await fireEvent.press(screen.getByRole("button", { name: "Sync with my TV" }));
  expect(props.onSync).toHaveBeenCalledTimes(1);
  await render(<SyncPanel {...props} state={{ kind: "matching", auto: true }} />);
  expect(screen.getByRole("button", { name: "Sync with my TV" })).toBeDisabled();
});

test("automatic syncing can be switched off", async () => {
  const props = await renderPanel({ kind: "idle" });
  await fireEvent(screen.getByLabelText("Keep in sync automatically"), "valueChange", false);
  expect(props.onAutoSyncChange).toHaveBeenCalledWith(false);
});
