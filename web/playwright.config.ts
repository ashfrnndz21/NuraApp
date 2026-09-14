import { generateKeyPairSync } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";

/** Where the app is. The default is the backend serving the build (`make build-web`, then
 *  `make dev`): one origin, the service worker registered, the way the phone will see it.
 *  `WEB_BASE_URL=http://127.0.0.1:5173/app/` runs the same flow against `make web` instead;
 *  the offline test needs the service worker and skips itself there. */
export const BASE_URL = process.env.WEB_BASE_URL ?? "http://127.0.0.1:8000/app/";

/** The API the tests seed through and the app calls (`make dev`). */
export const API_URL = process.env.NURA_BASE_URL ?? "http://127.0.0.1:8000";

/** The instant the backend's clock stands at for the whole run: 10 in the morning in
 *  Singapore on Monday 14 September, the same moment the phone's clock is fixed to
 *  (`fixClock`). The backend reads its own clock for the dose windows, the quiet hours and
 *  "today"; frozen, those do not drift with the hour the suite runs at. A test that means to
 *  cross the quiet hours or midnight moves it with `POST /dev/clock` (a dev run only). */
export const FROZEN_CLOCK = process.env.NURA_FROZEN_CLOCK ?? "2026-09-14T10:00:00+08:00";

/** Throwaway Web Push keys for this run of the suite, made here and never kept: the backend
 *  pushes by Web Push with them (ADR 0001), and no key is ever in the repo. A server already
 *  running locally keeps its own; the push test skips when it has none. */
const VAPID = (() => {
  const { privateKey } = generateKeyPairSync("ec", { namedCurve: "prime256v1" });
  const jwk = privateKey.export({ format: "jwk" }) as { d: string; x: string; y: string };
  const point = Buffer.concat([Buffer.from([4]), Buffer.from(jwk.x, "base64url"), Buffer.from(jwk.y, "base64url")]);
  return {
    NURA_VAPID_PUBLIC_KEY: point.toString("base64url"),
    NURA_VAPID_PRIVATE_KEY: jwk.d,
    NURA_VAPID_SUBJECT: "mailto:e2e@nura.invalid",
  };
})();

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
  // The backend: `make dev` (its env and its command), on the port the API URL names, with its
  // clock frozen at FROZEN_CLOCK. Build the app first (`make build-web`) so it serves /app.
  // Locally a server already running is reused — start it with NURA_FROZEN_CLOCK too, or stop
  // it and let this start one; the feed tests check the clock and say so if it is not frozen.
  webServer: {
    command: "make -C .. dev",
    url: `${API_URL}/health`,
    env: { UVICORN_PORT: new URL(API_URL).port || "8000", NURA_FROZEN_CLOCK: FROZEN_CLOCK, ...VAPID },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
