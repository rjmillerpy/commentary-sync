import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import MicCheck from "@/components/MicCheck";
import type { MicrophoneValue } from "@/hooks/useMicrophone";
import { MICROPHONES } from "../_fakeMedia";

function microphone(overrides: Partial<MicrophoneValue> = {}): MicrophoneValue {
  return {
    devices: MICROPHONES.filter((device) => device.kind === "audioinput") as MediaDeviceInfo[],
    deviceId: null,
    stream: null,
    level: 0.42,
    error: null,
    choose: jest.fn(),
    ...overrides,
  };
}

test("shows the level as a meter", () => {
  render(<MicCheck microphone={microphone()} isLocked={false} />);
  const meter = screen.getByRole("meter");
  expect(meter).toHaveAttribute("value", "42");
  expect(meter).toHaveAttribute("aria-valuetext", "42%");
});

test("lists the microphones, with a fallback name for unlabelled ones", () => {
  const unlabelled = { kind: "audioinput", deviceId: "x", label: "", groupId: "g" } as MediaDeviceInfo;
  render(<MicCheck microphone={microphone({ devices: [unlabelled] })} isLocked={false} />);
  expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["Browser default", "Microphone 1"]);
});

test.each([
  ["a microphone", "USB Microphone", "usb-mic"],
  ["the browser default", "Browser default", null],
])("choosing %s", async (_case, label, expected) => {
  const value = microphone({ deviceId: "default" });
  render(<MicCheck microphone={value} isLocked={false} />);
  await userEvent.selectOptions(screen.getByLabelText("Microphone"), label);
  expect(value.choose).toHaveBeenCalledWith(expected);
});

test.each([
  ["while live", microphone(), true],
  ["before any microphone is found", microphone({ devices: [] }), false],
])("the choice is locked %s", (_case, value, isLocked) => {
  render(<MicCheck microphone={value} isLocked={isLocked} />);
  expect(screen.getByLabelText("Microphone")).toBeDisabled();
});

test("shows why the microphone didn't open", () => {
  render(<MicCheck microphone={microphone({ error: "No microphone found. Plug one in and try again." })} isLocked={false} />);
  expect(screen.getByRole("alert")).toHaveTextContent("No microphone found");
});
