import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EventPicker from "@/components/EventPicker";
import { EVENTS, FakeApi, FINAL_GAME } from "../_fakeApi";

let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi().on("GET", "/events?limit=100", { status: 200, body: EVENTS }).install();
});

test("lists only games that can still be commentated", async () => {
  render(<EventPicker chosenId={null} isLocked={false} onChoose={jest.fn()} />);
  expect(screen.getByText("Loading games…")).toBeInTheDocument();
  const options = await screen.findAllByRole("radio");
  expect(options.map((option) => (option as HTMLInputElement).value)).toEqual(["e-live", "e-later"]);
});

test("passes the choice up", async () => {
  const onChoose = jest.fn();
  render(<EventPicker chosenId={null} isLocked={false} onChoose={onChoose} />);
  await userEvent.click(await screen.findByLabelText(/Lakers at Celtics/));
  expect(onChoose).toHaveBeenCalledWith("e-later");
});

test("says when nothing is on", async () => {
  fake.on("GET", "/events?limit=100", { status: 200, body: { ...EVENTS, items: [FINAL_GAME] } });
  render(<EventPicker chosenId={null} isLocked={false} onChoose={jest.fn()} />);
  expect(await screen.findByText("No games on or coming up.")).toBeInTheDocument();
});

test.each([
  ["the API's reason", { status: 503, body: { detail: "Service unavailable" } }, "Service unavailable"],
  ["a plain sentence", { status: 200, body: { items: "nope" } }, "Couldn't load games."],
])("a failure shows %s", async (_case, reply, message) => {
  fake.on("GET", "/events?limit=100", reply);
  render(<EventPicker chosenId={null} isLocked={false} onChoose={jest.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});

test("unmounting before the games arrive changes nothing", async () => {
  const { unmount } = render(<EventPicker chosenId={null} isLocked={false} onChoose={jest.fn()} />);
  unmount();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(fake.requests).toHaveLength(1);
});
