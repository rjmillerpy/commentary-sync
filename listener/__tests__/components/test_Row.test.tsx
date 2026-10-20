import { fireEvent, render, screen } from "@testing-library/react-native";

import { Row } from "@/components/Row";

test("a row is a button named by its title, with its detail and badge", async () => {
  const onPress = jest.fn();
  await render(<Row title="Texans at Jaguars" detail="NFL · CBS" badge="LIVE" onPress={onPress} />);
  expect(screen.getByText("NFL · CBS")).toBeOnTheScreen();
  expect(screen.getByText("LIVE")).toBeOnTheScreen();
  await fireEvent.press(screen.getByRole("button", { name: "Texans at Jaguars" }));
  expect(onPress).toHaveBeenCalledTimes(1);
});

test("without a badge there is none", async () => {
  await render(<Row title="Later game" detail="NBA" onPress={jest.fn()} />);
  expect(screen.queryByText("LIVE")).toBeNull();
});
