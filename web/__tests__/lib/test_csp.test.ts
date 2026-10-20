import { contentSecurityPolicy } from "@/lib/csp";

const PRODUCTION = { apiUrl: "https://api.example.com/", livekitUrl: "wss://live.example.com", isDevelopment: false };

function directives(policy: string): Record<string, string[]> {
  return Object.fromEntries(
    policy.split("; ").map((directive) => {
      const [name, ...sources] = directive.split(" ");
      return [name!, sources];
    }),
  );
}

test("scripts: the studio's own, this request's nonce, and the sync worklet's blob", () => {
  const policy = directives(contentSecurityPolicy("abc", PRODUCTION));
  expect(policy["script-src"]).toEqual(["'self'", "'nonce-abc'", "blob:"]);
  expect(policy["style-src"]).toEqual(["'self'"]);
});

test("connections: the API and LiveKit, and nothing else", () => {
  const policy = directives(contentSecurityPolicy("abc", PRODUCTION));
  expect(policy["connect-src"]).toEqual([
    "'self'",
    "https://api.example.com",
    "wss://live.example.com",
    "https://live.example.com",
  ]);
});

test("locally, plain ws and http", () => {
  const policy = directives(
    contentSecurityPolicy("abc", { apiUrl: "http://localhost:8000", livekitUrl: "ws://localhost:7880", isDevelopment: false }),
  );
  expect(policy["connect-src"]).toEqual(["'self'", "http://localhost:8000", "ws://localhost:7880", "http://localhost:7880"]);
});

test("never framed, no plugins, no base or form hijacking", () => {
  const policy = directives(contentSecurityPolicy("abc", PRODUCTION));
  expect([policy["frame-ancestors"], policy["object-src"], policy["base-uri"], policy["form-action"]]).toEqual([
    ["'none'"],
    ["'none'"],
    ["'none'"],
    ["'self'"],
  ]);
});

test("next dev needs eval and inline styles; a production build doesn't", () => {
  const policy = directives(contentSecurityPolicy("abc", { ...PRODUCTION, isDevelopment: true }));
  expect(policy["script-src"]).toContain("'unsafe-eval'");
  expect(policy["style-src"]).toContain("'unsafe-inline'");
});
