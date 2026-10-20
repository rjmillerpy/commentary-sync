import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SignIn from "@/components/SignIn";
import { FakeApi, PAIR } from "../_fakeApi";
import { MemoryStore } from "../_memoryStore";
import { renderSignedOut } from "../_render";

let fake: FakeApi;

beforeEach(() => {
  fake = new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .install();
});

async function fill(fields: Record<string, string>) {
  for (const [label, value] of Object.entries(fields)) await userEvent.type(screen.getByLabelText(label), value);
}

test("signs in with email and password", async () => {
  const store = new MemoryStore();
  renderSignedOut(<SignIn />, store);
  await fill({ Email: "fan@example.com", Password: "correct horse battery" });
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => expect(store.token).toBe("refresh-1"));
  expect(fake.requests[0]!.body).toEqual({ email: "fan@example.com", password: "correct horse battery" });
});

test("creates an account with a display name", async () => {
  renderSignedOut(<SignIn />);
  await userEvent.click(screen.getByRole("button", { name: "Create an account instead" }));
  expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
  await fill({ "Display name": "Fan", Email: "fan@example.com", Password: "correct horse battery" });
  await userEvent.click(screen.getByRole("button", { name: "Create account" }));
  await waitFor(() => expect(fake.paths()).toEqual(["POST /auth/register"]));
  expect(fake.requests[0]!.body).toEqual({ email: "fan@example.com", password: "correct horse battery", display_name: "Fan" });
});

test("switches back to signing in", async () => {
  renderSignedOut(<SignIn />);
  await userEvent.click(screen.getByRole("button", { name: "Create an account instead" }));
  await userEvent.click(screen.getByRole("button", { name: "I already have an account" }));
  expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();
});

test.each([
  ["sign-in", "current-password", null],
  ["register", "new-password", "12"],
])("the password field in %s mode follows the API's rules", async (mode, autoComplete, minLength) => {
  renderSignedOut(<SignIn />);
  if (mode === "register") await userEvent.click(screen.getByRole("button", { name: "Create an account instead" }));
  const password = screen.getByLabelText("Password");
  expect(password).toHaveAttribute("autocomplete", autoComplete);
  expect(password.getAttribute("minlength")).toBe(minLength);
  expect(password).toHaveAttribute("maxlength", "256");
});

test.each([
  ["the API's reason", { status: 401, body: { detail: "Wrong email or password" } }, "Wrong email or password"],
  ["a plain sentence when offline", null, "Can't reach the server. Check your connection and try again."],
])("a failed sign-in shows %s and can be tried again", async (_case, reply, message) => {
  if (reply === null) fake.offline = true;
  else fake.on("POST", "/auth/login", reply);
  renderSignedOut(<SignIn />);
  await fill({ Email: "fan@example.com", Password: "wrong" });
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
});

test("a failure that isn't the API's is still explained", async () => {
  fake.on("POST", "/auth/login", { status: 200, body: { unexpected: true } });
  renderSignedOut(<SignIn />);
  await fill({ Email: "fan@example.com", Password: "pw" });
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong; try again.");
});
