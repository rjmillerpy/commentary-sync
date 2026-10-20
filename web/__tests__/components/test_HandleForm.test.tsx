import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HandleForm from "@/components/HandleForm";
import { COMMENTATOR, type FakeApi, studioApi } from "../_fakeApi";
import { renderSignedIn } from "../_render";

let fake: FakeApi;

beforeEach(() => {
  fake = studioApi().on("POST", "/commentators", { status: 201, body: COMMENTATOR });
});

async function submit(handle: string) {
  await userEvent.type(screen.getByLabelText("Handle"), handle);
  await userEvent.click(screen.getByRole("button", { name: "Become a commentator" }));
}

test("creates the profile and hands it on", async () => {
  const onCreated = jest.fn();
  renderSignedIn(<HandleForm onCreated={onCreated} />);
  await submit("fan_cast");
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ handle: "fan_cast" })));
  expect(fake.requests.at(-1)).toMatchObject({ path: "/commentators", body: { handle: "fan_cast" } });
});

test("the field follows the API's handle rules", () => {
  renderSignedIn(<HandleForm onCreated={jest.fn()} />);
  const field = screen.getByLabelText("Handle");
  expect(field).toHaveAttribute("pattern", "[A-Za-z0-9_]+");
  expect(field).toHaveAttribute("minlength", "3");
  expect(field).toHaveAttribute("maxlength", "30");
});

test.each([
  ["a taken handle", { status: 409, body: { detail: "Handle already taken" } }, "Handle already taken"],
  ["a reply of the wrong shape", { status: 201, body: {} }, "Something went wrong; try again."],
])("%s is explained", async (_case, reply, message) => {
  fake.on("POST", "/commentators", reply);
  const onCreated = jest.fn();
  renderSignedIn(<HandleForm onCreated={onCreated} />);
  await submit("fan_cast");
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(onCreated).not.toHaveBeenCalled();
});
