import { SessionProvider, useSession } from "@commentary-sync/client/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { Text } from "react-native";

import { Session } from "@/lib/session";
import { SignInScreen } from "@/screens/SignInScreen";
import { listenerApi } from "../_render";

function Status() {
  return <Text>{`status: ${useSession().status}`}</Text>;
}

async function renderSignIn() {
  await render(
    <SessionProvider createSession={() => new Session()}>
      <SignInScreen />
      <Status />
    </SessionProvider>,
  );
}

test("signing in with email and password", async () => {
  const fake = listenerApi();
  await renderSignIn();
  await fireEvent.changeText(screen.getByLabelText("Email"), "fan@example.com");
  await fireEvent.changeText(screen.getByLabelText("Password"), "correct horse battery");
  await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => expect(screen.getByText("status: signed-in")).toBeOnTheScreen());
  expect(fake.requests[0]?.body).toEqual({ email: "fan@example.com", password: "correct horse battery" });
});

test("creating an account instead asks for a display name", async () => {
  const fake = listenerApi();
  await renderSignIn();
  await fireEvent.press(screen.getByRole("button", { name: "Create an account instead" }));
  expect(screen.getByRole("header", { name: "Create an account" })).toBeOnTheScreen();
  await fireEvent.changeText(screen.getByLabelText("Display name"), "Fan");
  await fireEvent.changeText(screen.getByLabelText("Email"), "fan@example.com");
  await fireEvent.changeText(screen.getByLabelText("Password"), "correct horse battery");
  await fireEvent.press(screen.getByRole("button", { name: "Create account" }));
  await waitFor(() => expect(screen.getByText("status: signed-in")).toBeOnTheScreen());
  expect(fake.paths()).toEqual(["POST /auth/register"]);
  await fireEvent.press(screen.getByRole("button", { name: "I have an account" }));
});

test("the API's refusal is shown, and the form can be sent again", async () => {
  listenerApi().on("POST", "/auth/login", { status: 401, body: { detail: "Wrong email or password" } });
  await renderSignIn();
  await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password");
  expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
});

test("a failure that isn't the API's is still explained", async () => {
  listenerApi();
  globalThis.fetch = (async () => ({ ok: true, status: 200, json: async () => ({}) })) as unknown as typeof fetch;
  await renderSignIn();
  await fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't sign in; try again.");
});
