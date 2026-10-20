/**
 * @jest-environment node
 */
import { NextRequest } from "next/server";

import { config, CSP_HEADER, middleware } from "@/middleware";

function page(): NextRequest {
  return new NextRequest("http://localhost:3000/");
}

test("every page gets a policy with a fresh nonce, on the response and for Next", () => {
  const first = middleware(page());
  const second = middleware(page());
  const policy = first.headers.get(CSP_HEADER)!;
  const nonce = /'nonce-([^']+)'/.exec(policy)![1];
  expect(nonce).toBeTruthy();
  expect(second.headers.get(CSP_HEADER)).not.toBe(policy);
  // NextResponse.next passes request headers on as x-middleware-request-*
  expect(first.headers.get(`x-middleware-request-${CSP_HEADER.toLowerCase()}`)).toBe(policy);
});

test("the policy allows the configured API and LiveKit", () => {
  const policy = middleware(page()).headers.get(CSP_HEADER)!;
  expect(policy).toContain("connect-src 'self' http://localhost:8000 ws://localhost:7880 http://localhost:7880");
});

test("static files and prefetches are left alone", () => {
  const [matcher] = config.matcher;
  const pattern = new RegExp(`^${matcher!.source}$`);
  expect(pattern.test("/")).toBe(true);
  expect(pattern.test("/_next/static/chunks/app.js")).toBe(false);
  expect(pattern.test("/icon.svg")).toBe(false);
  expect(matcher!.missing.map((rule) => rule.key)).toEqual(["next-router-prefetch", "purpose"]);
});
