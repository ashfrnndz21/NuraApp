import { expect, test } from "@playwright/test";
import { fixClock, openMe, signInThroughTheApp, todayReady } from "./helpers";
import { seedHome } from "./homeSeed";

/** The phone frame (owner's scope change 2026-09-21, docs/design/README.md item 7): above 600px
 *  wide, the whole app renders inside a 390px device frame on a plain dark page; below 600px (a
 *  real phone) there is no frame — full-bleed, exactly a phone app. Everything the app draws —
 *  the tab bar, a sheet — has to stay inside the frame on a wide screen. */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

test("above 600px: the frame exists, is 390px wide, and the tab bar sits inside it", async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const frame = page.locator("#phone-frame");
  await expect(frame).toBeVisible();
  const frameBox = (await frame.boundingBox())!;
  expect(Math.round(frameBox.width)).toBe(390);
  expect(frameBox.height).toBeLessThanOrEqual(844.5);

  const bar = page.locator("nav.tabbar");
  await expect(bar).toBeVisible();
  const barBox = (await bar.boundingBox())!;
  expect(barBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
  expect(barBox.x + barBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
  expect(barBox.y).toBeGreaterThanOrEqual(frameBox.y - 1);
  expect(barBox.y + barBox.height).toBeLessThanOrEqual(frameBox.y + frameBox.height + 1);

  // A plain dark page around the frame — the ground colour, not the app's own atmosphere.
  const pageGround = await page.evaluate(() => getComputedStyle(document.querySelector(".page-ground")!).backgroundColor);
  expect(pageGround).toBe("rgb(21, 17, 29)"); // #15111d
});

test("below 600px: there is no frame — the shell fills the viewport exactly like a phone app", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const frame = page.locator("#phone-frame");
  const frameBox = (await frame.boundingBox())!;
  // Full-bleed: the frame fills the whole viewport, no bezel, no radius.
  expect(Math.round(frameBox.width)).toBe(390);
  expect(Math.round(frameBox.height)).toBe(844);
  expect(frameBox.x).toBe(0);
  expect(frameBox.y).toBe(0);
  const radius = await frame.evaluate((el) => getComputedStyle(el).borderRadius);
  expect(radius).toBe("0px");
});

test("a sheet opened above 600px lies inside the frame, not the full browser window", async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const pa = await seedHome(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const frameBox = (await page.locator("#phone-frame").boundingBox())!;
  await openMe(page);
  const sheet = page.getByTestId("me-sheet");
  await expect(sheet).toBeVisible();
  const sheetBox = (await sheet.boundingBox())!;
  expect(sheetBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
  expect(sheetBox.x + sheetBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
  expect(sheetBox.y).toBeGreaterThanOrEqual(frameBox.y - 1);
  expect(sheetBox.y + sheetBox.height).toBeLessThanOrEqual(frameBox.y + frameBox.height + 1);
});
