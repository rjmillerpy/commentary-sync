import { test as base } from "@playwright/test";

/** Playwright's test, with one check added to every test: no page broke its
 * Content-Security-Policy. A violation means the studio's policy
 * (web/src/lib/csp.ts) blocked something the studio needs, or something it
 * shouldn't be doing at all. */
export const test = base.extend<{ cspViolations: string[] }>({
  cspViolations: [
    async ({ context }, use) => {
      const violations: string[] = [];
      context.on("console", (message) => {
        if (message.text().includes("Content Security Policy")) violations.push(message.text());
      });
      await use(violations);
      if (violations.length > 0) throw new Error(`CSP violations:\n${violations.join("\n")}`);
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
