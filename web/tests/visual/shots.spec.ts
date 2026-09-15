import { mkdirSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { fixClock, openMe, signInThroughTheApp, todayReady } from "../e2e/helpers";
import { seedHome } from "../e2e/homeSeed";

/** The design review's pictures (D1), not a gate: his Today, her Home, sign-in, both tab bars
 *  and the Me sheet, at 390 by 844 and 360 by 640, with the demo banner off and on, from the
 *  same seeded family the design suite uses. Each screen twice: what the phone shows first, and
 *  the whole page with its tab bar at the end ("-full"). */

const OUT = process.env.NURA_DESIGN_SHOTS ?? "design-shots";
mkdirSync(OUT, { recursive: true });

const SIZES = [
  { name: "390x844", width: 390, height: 844 },
  { name: "360x640", width: 360, height: 640 },
] as const;

async function phone(browser: Browser, size: (typeof SIZES)[number], demo: { on: boolean }): Promise<Page> {
  const context = await browser.newContext({ baseURL: BASE_URL, viewport: { width: size.width, height: size.height }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, timezoneId: "Asia/Singapore", serviceWorkers: "block" });
  const page = await context.newPage();
  await fixClock(page);
  await page.route("**/api/deployment", (route) => route.fulfill({ json: { region: "SG", demo: demo.on, push_key: null } }));
  return page;
}

async function snap(page: Page, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
  await page.evaluate(() => document.documentElement.classList.add("shot-full"));
  await page.screenshot({ path: `${OUT}/${name}-full.png`, fullPage: true, animations: "disabled" });
  await page.evaluate(() => document.documentElement.classList.remove("shot-full"));
}

test("his Today, her Home, sign-in, the tab bars and Me, at two sizes, banner off and on", async ({ browser, request }) => {
  const family = await seedHome(request);
  for (const size of SIZES) {
    for (const on of [false, true]) {
      const demo = { on };
      const tag = `${size.name}-${on ? "demo" : "plain"}`;

      const signIn = await phone(browser, size, demo);
      await signIn.goto("./");
      await expect(signIn.getByLabel("Your phone number")).toBeVisible();
      if (on) await expect(signIn.getByTestId("demo-banner")).toBeVisible();
      await snap(signIn, `signin-patient-${tag}`);
      await signIn.evaluate(() => (document.documentElement.dataset.density = "caregiver"));
      await snap(signIn, `signin-caregiver-${tag}`);
      await signIn.context().close();

      const his = await phone(browser, size, demo);
      await signInThroughTheApp(his, family.phone, "Pa");
      await todayReady(his);
      await expect(his.getByTestId("family-note")).toBeVisible();
      await snap(his, `dad-today-${tag}`);
      if (!on) await his.locator("nav.tabbar").screenshot({ path: `${OUT}/tabbar-patient-${size.name}.png` });
      await openMe(his);
      await his.evaluate(() => document.fonts.ready);
      await his.screenshot({ path: `${OUT}/me-sheet-patient-${tag}.png`, animations: "disabled" });
      await his.context().close();

      const hers = await phone(browser, size, demo);
      await signInThroughTheApp(hers, family.meiPhone, "Mei");
      await hers.getByTestId("door-key").click();
      await todayReady(hers);
      await expect(hers.getByTestId("home-hero")).toBeVisible();
      await snap(hers, `chief-home-${tag}`);
      if (!on) await hers.locator("nav.tabbar").screenshot({ path: `${OUT}/tabbar-caregiver-${size.name}.png` });
      await openMe(hers);
      await hers.evaluate(() => document.fonts.ready);
      await hers.screenshot({ path: `${OUT}/me-sheet-caregiver-${tag}.png`, animations: "disabled" });
      await hers.context().close();
    }
  }
});
