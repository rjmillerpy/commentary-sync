import { REFRESH_TOKEN_KEY, secureStorage } from "@/lib/tokenStore";
import { failure, items } from "../_fakeSecureStore";

test("the refresh token is kept in secure storage, and removed", async () => {
  secureStorage.write("refresh-1");
  expect(items.get(REFRESH_TOKEN_KEY)).toBe("refresh-1");
  expect(secureStorage.read()).toBe("refresh-1");
  secureStorage.write(null);
  await Promise.resolve(); // the delete is asynchronous
  expect(secureStorage.read()).toBeNull();
});

test("unavailable storage reads as empty and ignores writes", () => {
  failure.enabled = true;
  expect(secureStorage.read()).toBeNull();
  expect(() => secureStorage.write("refresh-1")).not.toThrow();
  expect(() => secureStorage.write(null)).not.toThrow();
});
