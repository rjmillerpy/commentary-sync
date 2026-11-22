import { fireEvent, render, screen } from "@testing-library/react-native";

import { PlaceholderRows, Row } from "@/components/Row";

test("a row shows its title and details, and says all of it to a screen reader", async () => {
  const onPress = jest.fn();
  await render(<Row title="Texans at Jaguars" details={["2 commentators live", "NFL · Sun 1:00 PM"]} isLive onPress={onPress} />);
  expect(screen.getByText("● LIVE")).toBeOnTheScreen();
  const row = screen.getByRole("button", { name: "Texans at Jaguars, 2 commentators live, NFL · Sun 1:00 PM, live" });
  await fireEvent.press(row);
  expect(onPress).toHaveBeenCalled();
});

test("a row that isn't live has no badge", async () => {
  await render(<Row title="Later" details={[]} onPress={jest.fn()} />);
  expect(screen.queryByText("● LIVE")).toBeNull();
});

test("placeholders stand in while a list loads", async () => {
  await render(<PlaceholderRows count={2} />);
  expect(screen.getByLabelText("Loading")).toBeOnTheScreen();
});
