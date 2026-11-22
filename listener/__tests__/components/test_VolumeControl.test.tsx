import { fireEvent, render, screen } from "@testing-library/react-native";

import { VolumeControl } from "@/components/VolumeControl";

const props = (overrides = {}) => ({ volume: 0.5, onVolume: jest.fn(), isMuted: false, onMute: jest.fn(), ...overrides });

test("quieter and louder step by a tenth", async () => {
  const value = props();
  await render(<VolumeControl {...value} />);
  expect(screen.getByLabelText("Commentary volume 5 of 10")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Quieter" }));
  await fireEvent.press(screen.getByRole("button", { name: "Louder" }));
  expect(value.onVolume.mock.calls).toEqual([[0.4], [0.6]]);
});

test("its own mute, which says it's muted", async () => {
  const value = props({ isMuted: true });
  await render(<VolumeControl {...value} />);
  expect(screen.getByLabelText("Commentary muted")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Unmute commentary" }));
  expect(value.onMute).toHaveBeenCalledWith(false);
});

test.each([
  [0, "Quieter"],
  [1, "Louder"],
])("at %s, no further that way", async (volume, button) => {
  await render(<VolumeControl {...props({ volume })} />);
  expect(screen.getByRole("button", { name: button })).toBeDisabled();
});

test("mute from unmuted", async () => {
  const value = props();
  await render(<VolumeControl {...value} />);
  await fireEvent.press(screen.getByRole("button", { name: "Mute commentary" }));
  expect(value.onMute).toHaveBeenCalledWith(true);
});
