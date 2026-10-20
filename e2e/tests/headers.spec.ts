import { API_URL, STUDIO_URL } from "../support/stack";
import { expect, test } from "../support/fixtures";

test("the studio's pages carry a CSP whose nonce is on every script", async ({ request }) => {
  const response = await request.get(STUDIO_URL);
  const policy = response.headers()["content-security-policy"] ?? "";
  const nonce = /'nonce-([^']+)'/.exec(policy)?.[1];
  expect(nonce, policy).toBeTruthy();
  expect(policy).toContain("frame-ancestors 'none'");
  const html = await response.text();
  const scripts = html.match(/<script\b[^>]*>/g) ?? [];
  expect(scripts.length).toBeGreaterThan(0);
  expect(scripts.filter((tag) => !tag.includes(`nonce="${nonce}"`))).toEqual([]);
  // A second load gets a nonce of its own.
  const again = (await request.get(STUDIO_URL)).headers()["content-security-policy"];
  expect(again).not.toBe(policy);
});

test("the API's answers can't be used as pages", async ({ request }) => {
  const headers = (await request.get(`${API_URL}/health/live`)).headers();
  expect(headers["content-security-policy"]).toContain("default-src 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
});
