import { renderHook } from "@testing-library/react-native";

import { useAuthorized } from "@/hooks/useAccess";
import { listenerApi, withAccess } from "../_render";

test("calls get a guest token, fetched once for the whole app", async () => {
  const fake = listenerApi();
  const { result } = await renderHook(useAuthorized, { wrapper: withAccess });
  expect(await result.current(async (token) => token)).toBe("guest-1");
  expect(await result.current(async (token) => token)).toBe("guest-1");
  expect(fake.paths()).toEqual(["POST /auth/guest"]);
});

test("without the provider it says what's missing", async () => {
  jest.spyOn(console, "error").mockImplementation(() => undefined);
  await expect(renderHook(useAuthorized)).rejects.toThrow("useAuthorized needs an AccessProvider above it");
});
