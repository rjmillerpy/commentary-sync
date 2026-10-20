import { render, screen } from "@testing-library/react";

import StudioPage from "@/app/page";
import { FakeApi } from "../_fakeApi";

beforeEach(() => {
  window.sessionStorage.clear();
  new FakeApi().install();
});

test("smoke: the page renders the studio, signed out", () => {
  render(<StudioPage />);
  expect(screen.getByRole("heading", { level: 1, name: "Studio" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Sign in to the studio" })).toBeInTheDocument();
});
