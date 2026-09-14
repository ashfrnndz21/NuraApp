import { expect, test } from "@playwright/test";
import { freshPhone, keptExpiry, signInThroughTheApp } from "./helpers";

/** Today across midnight in Singapore. The page read at 23:59 is not shown after 00:00: the
 *  app reads the new day's page itself, the date and the greeting turn over, the phone's copy
 *  now lasts until the next midnight, and an empty Today still says there are no medicines —
 *  never nothing at all. */
test("crossing midnight in Singapore: Today reads the new day and still says no medicines", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-09-14T15:59:00Z") }); // 23:59 in Singapore
  await signInThroughTheApp(page, freshPhone(), "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  // Onboarding comes next (W3); this test is Today's, so set up later.
  await page.getByTestId("set-up-later").click();

  // Just before midnight.
  await expect(page.getByTestId("no-medicines")).toContainText("Nura has no medicines for you yet.");
  await expect(page.locator(".hero .date")).toHaveText("Monday 14 September");
  await expect(page.locator(".hero .greeting")).toHaveText("Good evening, Pa.");
  await expect.poll(() => keptExpiry(page)).toBe("2026-09-14T16:00:00.000Z");

  // Just after it: no reload by hand.
  await page.clock.fastForward("01:30");
  await expect(page.locator(".hero .date")).toHaveText("Tuesday 15 September");
  await expect(page.locator(".hero .greeting")).toHaveText("Good morning, Pa.");
  await expect(page.getByTestId("no-medicines")).toContainText("Nura has no medicines for you yet.");
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect(page.locator("nav.tabbar")).toBeVisible();
  await expect.poll(() => keptExpiry(page)).toBe("2026-09-15T16:00:00.000Z");
});
