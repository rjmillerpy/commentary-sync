import { render, screen } from "@testing-library/react-native";

import { Notice } from "@/components/Notice";

test("a notice is plain text", async () => {
  await render(<Notice text="Nothing yet." />);
  expect(screen.getByText("Nothing yet.")).toBeOnTheScreen();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("an error is announced as an alert", async () => {
  await render(<Notice text="Offline." isError />);
  expect(screen.getByRole("alert")).toHaveTextContent("Offline.");
});
