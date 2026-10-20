import { REFRESH_TOKEN_KEY } from "@/lib/tokenStore";
import { Session } from "@/lib/session";
import { items } from "../_fakeSecureStore";
import { listenerApi } from "../_render";

// The session's behaviour is tested with the shared client (client/test).
// Here: that the app's session calls the app's API and keeps its token securely.

test("signing in keeps the refresh token in secure storage", async () => {
  const fake = listenerApi();
  const session = new Session();
  await session.signIn("fan@example.com", "pw");
  expect(items.get(REFRESH_TOKEN_KEY)).toBe("refresh-1");
  expect(fake.paths()).toEqual(["POST /auth/login"]);
});

test("a token already in secure storage can be restored", () => {
  items.set(REFRESH_TOKEN_KEY, "refresh-1");
  expect(new Session().canRestore).toBe(true);
});
