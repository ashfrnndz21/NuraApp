import { defineConfig, devices } from "@playwright/test";

/** Where the app is. The default is the backend serving the build (`make build-web`, then
 *  `make dev`): one origin, the service worker registered, the way the phone will see it.
 *  `WEB_BASE_URL=http://127.0.0.1:5173/app/` runs the same flow against `make web` instead;
 *  the offline test needs the service worker and skips itself there. */
export const BASE_URL = process.env.WEB_BASE_URL ?? "http://127.0.0.1:8000/app/";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    ...devices["Pixel 5"],
    // The patient's phone: a small screen, touch, and the service worker allowed.
    serviceWorkers: "allow",
    // The phone is in Singapore, whatever zone the runner is in; the tests that are not
    // about the time also fix its clock (`fixClock`), and midnight has its own test.
    timezoneId: "Asia/Singapore",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Pixel 5"], browserName: "chromium" } }],
});
