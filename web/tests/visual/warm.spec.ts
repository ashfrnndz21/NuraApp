import { expect, test, type Browser, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { fixClock, signInThroughTheApp, todayReady } from "../e2e/helpers";
import { seedHome } from "../e2e/homeSeed";

/** The warm pass's pictures (docs/design-direction.md), for the owner: Welcome and Home at 390
 *  by 844 and 360 by 640, in both densities, with the demo banner off. Not a gate: `npm run shots
 *  -- warm.spec.ts` writes them into `tests/visual/warm/`, where they are kept in the repo so the
 *  owner can see what was built. Each screen twice: what the phone shows first, and the whole
 *  page ("-full"). */

const OUT = new URL("./warm/", import.meta.url).pathname;

const SIZES = [
  { name: "390x844", width: 390, height: 844 },
  { name: "360x640", width: 360, height: 640 },
] as const;

async function phone(browser: Browser, size: (typeof SIZES)[number]): Promise<Page> {
  const context = await browser.newContext({ baseURL: BASE_URL, viewport: { width: size.width, height: size.height }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, timezoneId: "Asia/Singapore", serviceWorkers: "block", reducedMotion: "reduce" });
  const page = await context.newPage();
  await fixClock(page);
  await page.route("**/api/deployment", (route) => route.fulfill({ json: { region: "SG", demo: false, push_key: null } }));
  return page;
}

async function snap(page: Page, name: string): Promise<void> {
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${OUT}${name}.png`, animations: "disabled" });
  await page.evaluate(() => document.documentElement.classList.add("shot-full"));
  await page.screenshot({ path: `${OUT}${name}-full.png`, fullPage: true, animations: "disabled", scale: "css" });
  await page.evaluate(() => document.documentElement.classList.remove("shot-full"));
}

test("Welcome and Home, warm, at two sizes and in both densities", async ({ browser, request }) => {
  test.setTimeout(600_000);
  for (const size of SIZES) {
    const welcome = await phone(browser, size);
    await welcome.goto("./");
    await expect(welcome.getByTestId("welcome-screen")).toBeVisible();
    for (const density of ["patient", "caregiver"] as const) {
      await welcome.evaluate((d) => (document.documentElement.dataset.density = d), density);
      await snap(welcome, `welcome-${density}-${size.name}`);
    }
    await welcome.context().close();

    const family = await seedHome(request);
    // His Home in his density, and the same phone in hers: density changes type and targets.
    const his = await phone(browser, size);
    await signInThroughTheApp(his, family.phone, "Pa");
    await todayReady(his);
    await snap(his, `home-patient-${size.name}`);
    await his.evaluate(() => (document.documentElement.dataset.density = "caregiver"));
    await snap(his, `home-own-caregiver-look-${size.name}`);
    await his.context().close();

    // Her Home: Mei holding Pa's key, in her density — said about him by name.
    const hers = await phone(browser, size);
    await signInThroughTheApp(hers, family.meiPhone, "Mei");
    await hers.getByTestId("door-key").click();
    await todayReady(hers);
    await snap(hers, `home-caregiver-${size.name}`);
    await hers.evaluate(() => (document.documentElement.dataset.density = "patient"));
    await snap(hers, `home-caregiver-patient-look-${size.name}`);
    await hers.getByTestId("do-activities").click();
    await expect(hers.getByTestId("soon-screen")).toBeVisible();
    await snap(hers, `soon-${size.name}`);
    await hers.context().close();
  }
});
