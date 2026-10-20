const ORIGINAL = process.env.NEXT_PUBLIC_API_URL;

async function apiUrlWith(value: string | undefined): Promise<string> {
  if (value === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = value;
  jest.resetModules();
  return (await import("@/lib/config")).API_URL;
}

afterEach(() => {
  process.env.NEXT_PUBLIC_API_URL = ORIGINAL;
});

test.each([
  ["unset", undefined, "http://localhost:8000"],
  ["set", "https://api.example.com", "https://api.example.com"],
  ["trailing slash", "https://api.example.com//", "https://api.example.com"],
])("the API URL when %s", async (_case, value, expected) => {
  expect(await apiUrlWith(value)).toBe(expected);
});

test("every call has a timeout", async () => {
  const { REQUEST_TIMEOUT_MS } = await import("@/lib/config");
  expect(REQUEST_TIMEOUT_MS).toBeGreaterThan(0);
});
