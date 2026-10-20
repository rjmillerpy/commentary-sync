import { defineConfig, devices } from "@playwright/test";

import { STUDIO_URL } from "./support/stack";
import { TONE_FILE } from "./support/tone";

export default defineConfig({
  testDir: "tests",
  globalSetup: "./support/global-setup.ts",
  outputDir: "results/artifacts",
  // One stack, shared: tests run one at a time so they don't contend for it.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: true,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  reporter: [["list"], ["html", { outputFolder: "results/report", open: "never" }]],
  use: {
    ...devices["Desktop Chrome"],
    // The full Chromium build in headless mode. The default headless shell
    // ignores --unsafely-treat-insecure-origin-as-secure, which leaves the
    // studio without navigator.mediaDevices.
    channel: "chromium",
    baseURL: STUDIO_URL,
    trace: "retain-on-failure",
    permissions: ["microphone"],
    launchOptions: {
      args: [
        // A microphone that plays the test tone, granted without a prompt.
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        `--use-file-for-fake-audio-capture=${TONE_FILE}`,
        // Listener pages play audio without a click.
        "--autoplay-policy=no-user-gesture-required",
        // getUserMedia needs a secure context. The studio is on http://web:3000
        // inside the e2e network, where TLS would only add a test certificate.
        `--unsafely-treat-insecure-origin-as-secure=${STUDIO_URL}`,
      ],
    },
  },
});
