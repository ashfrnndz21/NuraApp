import { expect, test } from "@playwright/test";
import { freshPhone, keptExpiry, signInThroughTheApp, todayReady } from "./helpers";

/** Today across midnight in Singapore. The page read at 23:59 is not shown after 00:00: the
 *  app reads the new day's page itself, the date and the greeting turn over, the phone's copy
 *  now lasts until the next midnight, and an empty Today still says there are no medicines —
 *  never nothing at all. */
test("crossing midnight in Singapore: Today reads the new day and still says no medicines", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-14T15:59:00Z") }); // 23:59 in Singapore
  await signInThroughTheApp(page, freshPhone(), "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("who-continue").click();
  await page.getByTestId("agree").click();
  // Onboarding comes next (W3); this test is Today's, so set up later.
  await page.getByTestId("set-up-later").click();

  // Just before midnight. A fresh owner with nothing yet is the quiet state (owner review
  // round 3, fix #5): the header's own greeting/question drop out then — the large one under
  // the orb (`quiet-greeting`) is the only one — so the date is what's checked in the header,
  // the greeting where the quiet state itself says it.
  await expect(page.getByTestId("no-medicines")).toContainText("Nura has no medicines for you yet.");
  await expect(page.getByTestId("home-head-date")).toHaveText("Monday 14 September");
  await expect(page.getByTestId("quiet-greeting").locator(".sr-only")).toHaveText("Good evening, Pa.");
  await expect.poll(() => keptExpiry(page)).toBe("2026-09-14T16:00:00.000Z");

  // Just after it: no reload by hand.
  await page.clock.fastForward("01:30");
  await expect(page.getByTestId("home-head-date")).toHaveText("Tuesday 15 September");
  await expect(page.getByTestId("quiet-greeting").locator(".sr-only")).toHaveText("Good morning, Pa.");
  await expect(page.getByTestId("no-medicines")).toContainText("Nura has no medicines for you yet.");
  await todayReady(page);
  await expect(page.locator("nav.tabbar")).toBeVisible();
  await expect.poll(() => keptExpiry(page)).toBe("2026-09-15T16:00:00.000Z");
});
