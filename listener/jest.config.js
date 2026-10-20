/** @type {import('jest').Config} */
module.exports = {
  preset: "jest-expo",
  setupFiles: ["<rootDir>/jest.setup.ts"],
  // Each test starts with empty secure storage and no players.
  setupFilesAfterEnv: ["<rootDir>/jest.reset.ts"],
  // Files starting with an underscore are shared test helpers, not suites.
  testPathIgnorePatterns: ["/node_modules/", "/__tests__/(.*/)?_[^/]+\\.tsx?$"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  collectCoverageFrom: ["index.ts", "src/**/*.{ts,tsx}"],
  coverageReporters: ["text-summary", "json-summary", "html"],
  // The same floor as the API and the studio.
  coverageThreshold: { global: { statements: 90, branches: 90, functions: 90, lines: 90 } },
};
