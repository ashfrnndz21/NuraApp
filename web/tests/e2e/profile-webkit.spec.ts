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
 *  WebKit is opt-in only (`playwright.config.ts`'s own comment): `NURA_E2E_WEBKIT=1 npx
 *  playwright test --project=webkit`. On chromium this walk still runs (the screens themselves
 *  are worth walking), but the freeze probe cannot fail chromium the way it could webkit, so
 *  the test is skipped there — the other specs already cover these screens on chromium. */
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
