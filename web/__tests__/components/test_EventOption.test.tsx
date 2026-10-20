import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EventOption from "@/components/EventOption";
import { EventSchema } from "@commentary-sync/client/schema";
import { LATER_GAME, LIVE_GAME } from "../_fakeApi";

function renderOption(game: unknown, props: Partial<{ isChosen: boolean; isDisabled: boolean }> = {}) {
  const onChoose = jest.fn();
  render(
    <ul>
      <EventOption event={EventSchema.parse(game)} isChosen={false} isDisabled={false} onChoose={onChoose} {...props} />
    </ul>,
  );
  return onChoose;
}

test("a live game says so, with its league and networks", () => {
  renderOption(LIVE_GAME);
  expect(screen.getByText("Houston Texans at Jacksonville Jaguars")).toBeInTheDocument();
  expect(screen.getByText(/NFL · Live now · CBS/)).toBeInTheDocument();
});

test("a later game shows when it starts, and no networks when it has none", () => {
  renderOption(LATER_GAME);
  const detail = screen.getByText(/^NBA · /);
  expect(detail).not.toHaveTextContent("Live now");
  expect(detail.textContent).not.toContain(" · CBS");
});

test("choosing it passes its ID", async () => {
  const onChoose = renderOption(LIVE_GAME);
  await userEvent.click(screen.getByRole("radio"));
  expect(onChoose).toHaveBeenCalledWith("e-live");
});

test.each([
  ["chosen", { isChosen: true }, true, false],
  ["locked while live", { isDisabled: true }, false, true],
])("%s", (_case, props, checked, disabled) => {
  renderOption(LIVE_GAME, props);
  const radio = screen.getByRole("radio");
  expect((radio as HTMLInputElement).checked).toBe(checked);
  expect((radio as HTMLInputElement).disabled).toBe(disabled);
});
