import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { AccessibilityInfo, Platform } from "react-native";

import { SyncIndicator } from "@/components/SyncIndicator";
import type { SyncStatus } from "@/lib/syncStatus";

const SYNCED: SyncStatus = { kind: "synced", label: "Synced with your TV", detail: null, action: null };
const OUT: SyncStatus = { kind: "desynced", label: "Out of sync · Tap to resync", detail: "Couldn't match your TV.", action: "sync" };
const SYNCING: SyncStatus = { kind: "syncing", label: "Listening to your TV…", detail: null, action: null };

afterEach(() => jest.restoreAllMocks());

test("in sync: words and an icon, nothing to tap, announced politely", async () => {
  await render(<SyncIndicator status={SYNCED} onAct={jest.fn()} />);
  const status = screen.getByTestId("sync-status");
  expect(screen.getByText("Synced with your TV")).toBeOnTheScreen();
  expect(screen.getByText("✓", { includeHiddenElements: true })).toBeOnTheScreen(); // decorative: the words say it
  expect(status).toBeDisabled();
  expect(status.props.accessibilityLiveRegion).toBe("polite");
});

test("out of sync: the status is the button, and announced at once", async () => {
  const onAct = jest.fn();
  await render(<SyncIndicator status={OUT} onAct={onAct} />);
  const status = screen.getByRole("button", { name: "Out of sync · Tap to resync. Couldn't match your TV." });
  expect(status.props.accessibilityLiveRegion).toBe("assertive");
  await fireEvent.press(status);
  expect(onAct).toHaveBeenCalledWith("sync");
});

test("syncing spins, unless the phone asks for less motion", async () => {
  jest.spyOn(AccessibilityInfo, "isReduceMotionEnabled").mockResolvedValue(true);
  await render(<SyncIndicator status={SYNCING} onAct={jest.fn()} />);
  await waitFor(() => expect(screen.getByText("↻", { includeHiddenElements: true })).toBeOnTheScreen());
});

test("the first time, it explains itself", async () => {
  await render(<SyncIndicator status={SYNCED} onAct={jest.fn()} showTip />);
  expect(screen.getByText(/This shows whether the commentary matches your TV/)).toBeOnTheScreen();
});

test("on iOS, every change is announced", async () => {
  const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
  const os = Platform.OS;
  Object.defineProperty(Platform, "OS", { value: "ios", configurable: true });
  try {
    await render(<SyncIndicator status={OUT} onAct={jest.fn()} />);
    expect(announce).toHaveBeenCalledWith("Out of sync · Tap to resync. Couldn't match your TV.");
  } finally {
    Object.defineProperty(Platform, "OS", { value: os, configurable: true });
  }
});
