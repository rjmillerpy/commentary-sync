import { render, screen } from "@testing-library/react";

import SyncNote from "@/components/SyncNote";

test("off says nothing", () => {
  const { container } = render(<SyncNote status="off" />);
  expect(container).toBeEmptyDOMElement();
});

test.each([
  ["on", /Listeners can sync their TVs to yours.*not in headphones/],
  ["unavailable", /TV sync is off/],
] as const)("%s tells the commentator", (status, text) => {
  render(<SyncNote status={status} />);
  expect(screen.getByRole("status")).toHaveTextContent(text);
});
