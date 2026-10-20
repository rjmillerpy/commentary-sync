import { render, screen } from "@testing-library/react";

import AudienceCount from "@/components/AudienceCount";

test.each([
  [0, "0 listening"],
  [1, "1 listening"],
  [12, "12 listening"],
])("%i listeners", (listeners, text) => {
  render(<AudienceCount listeners={listeners} />);
  expect(screen.getByRole("status")).toHaveTextContent(text);
});

test("unknown says nothing", () => {
  const { container } = render(<AudienceCount listeners={null} />);
  expect(container).toBeEmptyDOMElement();
});
