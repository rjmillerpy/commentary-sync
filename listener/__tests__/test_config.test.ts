const ORIGINAL = process.env.EXPO_PUBLIC_API_URL;

afterEach(() => {
  process.env.EXPO_PUBLIC_API_URL = ORIGINAL;
  jest.resetModules();
});

test("without a setting, the API is the local stack's", () => {
  delete process.env.EXPO_PUBLIC_API_URL;
  expect(jest.requireActual("@/config").API_URL).toBe("http://localhost:8000");
});

test("EXPO_PUBLIC_API_URL points the app at another API", () => {
  process.env.EXPO_PUBLIC_API_URL = "http://192.168.1.20:8000";
  expect(jest.requireActual("@/config").API_URL).toBe("http://192.168.1.20:8000");
});

test("API calls time out", () => {
  expect(jest.requireActual("@/config").REQUEST_TIMEOUT_MS).toBe(10_000);
});
