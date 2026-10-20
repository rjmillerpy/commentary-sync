import type { Config } from "jest";
// Explicit .js: Node 24 loads this file as native ESM, which needs the real
// filename since next has no export map for this subpath.
import nextJest from "next/jest.js";

const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  // Files starting with an underscore are shared test helpers, not suites.
  testPathIgnorePatterns: ["/node_modules/", "/\\.next/", "/__tests__/.*/_[^/]+\\.tsx?$", "/__tests__/_[^/]+\\.tsx?$"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  collectCoverageFrom: ["src/**/*.{ts,tsx}", "!src/**/*.d.ts"],
  coverageReporters: ["text-summary", "json-summary", "html"],
  // The same floor as the API (pyproject.toml).
  coverageThreshold: { global: { statements: 90, branches: 90, functions: 90, lines: 90 } },
};

export default createJestConfig(config);
