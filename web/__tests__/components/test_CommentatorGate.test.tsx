import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CommentatorGate from "@/components/CommentatorGate";
import { COMMENTATOR, type FakeApi, studioApi } from "../_fakeApi";
import { renderSignedIn } from "../_render";

let fake: FakeApi;

beforeEach(() => {
  fake = studioApi();
});

const gate = <CommentatorGate>{(commentator) => <p>Desk for {commentator.handle}</p>}</CommentatorGate>;

test("a commentator gets the studio", async () => {
  renderSignedIn(gate);
  expect(screen.getByText("Loading your profile…")).toBeInTheDocument();
  expect(await screen.findByText("Desk for fan_cast")).toBeInTheDocument();
});

test("anyone else picks a handle first, then gets the studio", async () => {
  fake
    .on("GET", "/commentators/me", { status: 404, body: { detail: "This account is not a commentator" } })
    .on("POST", "/commentators", { status: 201, body: COMMENTATOR });
  renderSignedIn(gate);
  await userEvent.type(await screen.findByLabelText("Handle"), "fan_cast");
  await userEvent.click(screen.getByRole("button", { name: "Become a commentator" }));
  expect(await screen.findByText("Desk for fan_cast")).toBeInTheDocument();
});

test.each([
  ["the API's reason", { status: 500, body: { detail: "Internal server error", request_id: "r" } }, "Internal server error"],
  ["a plain sentence", { status: 200, body: { nope: 1 } }, "Couldn't load your profile."],
])("a failure to load shows %s", async (_case, reply, message) => {
  fake.on("GET", "/commentators/me", reply);
  renderSignedIn(gate);
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
});
