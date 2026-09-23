import { expect, test } from "@playwright/test";
import { fixClock, seedOwner, signInThroughTheApp } from "./helpers";

/** D-0 (docs/design/audit-2026-09-22.md §5): on WebKit — Safari, the only engine on an iPhone —
 *  opening Profile froze the main thread within 500 ms, taking Insurance, Not well and the
 *  emergency card down with it (they sit downstream of the Profile tap in the audit's own
 *  walk). This walks the same path and asserts the main thread is still answering
 *  `page.evaluate` after each tap — the exact probe the audit used to prove the freeze
 *  (`page.evaluate(() => 1)` raced against a deadline) — so a regression here fails loudly
 *  instead of just timing out somewhere downstream with no clue which screen caused it.
 *
 *  Honestly, three limits on what this guards (review item 7):
 *  1. It runs in no automated gate today. WebKit is opt-in only (`playwright.config.ts`'s own
 *     comment): `NURA_E2E_WEBKIT=1 npx playwright test --project=webkit`. CI's own runner has
 *     no WebKit browser installed and installing one is off limits here (`.github` changes are
 *     not this task's to make) — so this walk currently only runs on a developer's own machine,
 *     on purpose, by hand.
 *  2. `test.skip` below means it does not run on chromium at all — it is not "the same walk,
 *      also run there for coverage"; chromium is skipped outright, because the freeze this
 *      guards against has no chromium equivalent to catch. The other chromium specs
 *      (`insurance.spec.ts`, `emergency.spec.ts`, `today.spec.ts`) already walk these same
 *      screens for their own reasons; this file adds nothing on chromium.
 *  3. The 10 s deadline in `stillResponsive` below catches a SUSTAINED freeze — the audit's
 *      own measurement was as long as 149 s in one run — not necessarily the first 500 ms of
 *      one that self-resolves before the check after that tap ever runs. A block shorter than
 *      whatever gap sits between the tap and the next `stillResponsive` call would not be
 *      caught here. */
test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("Profile, Insurance, Not well and the emergency card stay responsive on WebKit", async ({ page, request, browserName }) => {
  test.skip(browserName !== "webkit", "the WebKit main-thread freeze this guards against (D-0) has no chromium equivalent; run with NURA_E2E_WEBKIT=1 --project=webkit");

  const pa = await seedOwner(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("tab-home")).toBeVisible();

  // The exact probe the audit used: a one-line `page.evaluate` raced against a deadline. The
  // audit measured the hang lasting 149 s in one run; 10 s here is well past the 500 ms it took
  // to start and short enough that a real freeze still fails the test promptly.
  const stillResponsive = async (label: string): Promise<void> => {
    const alive = await Promise.race([
      page.evaluate(() => 1).then(() => true),
      new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 10_000)),
    ]);
    expect(alive, `${label}: the main thread did not answer page.evaluate within 10s (D-0)`).toBe(true);
  };

  await page.getByTestId("tab-profile").click();
  await stillResponsive("Profile");
  await expect(page.getByTestId("profile-screen")).toBeVisible();

  await page.getByTestId("profile-insurance").click();
  await stillResponsive("Insurance");
  await expect(page.getByTestId("insurance-screen")).toBeVisible();

  await page.getByTestId("tab-home").click();
  await expect(page.getByTestId("not-well")).toBeVisible();
  await page.getByTestId("not-well").click();
  await stillResponsive("Not well");
  await expect(page.getByTestId("not-well-screen")).toBeVisible();
  await page.getByTestId("not-well-words").fill("My chest feels tight and I am short of breath");
  await page.getByTestId("not-well-send").click();
  await expect(page.getByTestId("what-to-do-screen")).toBeVisible({ timeout: 15_000 });
  await stillResponsive("Not well answer");

  // The red-flag "What to do now" card has no tab bar by design (`WhatToDo.tsx`: "nothing
  // competes with the card") — its own "Back to Today" is the only way out.
  await page.getByTestId("back-today").click();
  await expect(page.getByTestId("tab-home")).toBeVisible();

  await page.getByTestId("tab-profile").click();
  await expect(page.getByTestId("me-emergency")).toBeVisible();
  await page.getByTestId("me-emergency").click();
  await stillResponsive("Emergency card");
  await expect(page.getByTestId("emergency-card")).toBeVisible();
});
