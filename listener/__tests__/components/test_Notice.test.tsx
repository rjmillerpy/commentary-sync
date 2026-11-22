import { fireEvent, render, screen } from "@testing-library/react-native";

import { Notice } from "@/components/Notice";

test("a plain notice is text", async () => {
  await render(<Notice text="Waiting…" />);
  expect(screen.getByText("Waiting…")).toBeOnTheScreen();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a problem is an alert with one way out", async () => {
  const onPress = jest.fn();
  await render(<Notice text="Couldn't load the games" isError action={{ label: "Try again", onPress }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load the games");
  await fireEvent.press(screen.getByRole("button", { name: "Try again" }));
  expect(onPress).toHaveBeenCalled();
});
