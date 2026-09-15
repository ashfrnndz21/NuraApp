import { mkdirSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { fixClock, freshPhone, openMe, signInThroughTheApp, todayReady } from "../e2e/helpers";
import { placeholderPng } from "../e2e/record-helpers";
import { seedHome } from "../e2e/homeSeed";

/** The design review's pictures (D1), not a gate: his Today, her Home, sign-in, both tab bars
 *  and the Me sheet, at 390 by 844 and 360 by 640, with the demo banner off and on, from a family seeded
 *  the way the design suite seeds one. Each screen twice: what the phone shows first, and
 *  the whole page with its tab bar at the end ("-full"). */

const OUT = process.env.NURA_DESIGN_SHOTS ?? "design-shots";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 15_000 });

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
  for (const size of SIZES) {
    for (const on of [false, true]) {
      // A family of its own each time: reading "What changed" is looking, so a second look at
      // the same family would find nothing new to show.
      const family = await seedHome(request);
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

/** Stage 2 (D1): every other screen in both densities — each tab, the feed, not feeling well,
 *  the symptom log, the emergency card, the review card and the start of setting up — at both
 *  sizes with the banner off, each as the phone shows it first and as a whole page. */
test("every other screen: the tabs, the feed, not feeling well, symptoms, the emergency and review cards, setting up", async ({ browser, request }) => {
  test.setTimeout(900_000);
  const off = { on: false };
  const settle = async (page: Page) => {
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => document.fonts.ready);
  };
  const eachTab = async (page: Page, who: string, tag: string) => {
    const tabs = page.locator("nav.tabbar button");
    const count = await tabs.count();
    for (let index = 1; index < count; index += 1) {
      const name = ((await tabs.nth(index).innerText()).trim().toLowerCase() || `tab${index}`).replace(/\W+/g, "-");
      await tabs.nth(index).click();
      await settle(page);
      await snap(page, `${who}-${name}-${tag}`);
    }
    await tabs.nth(0).click();
    await todayReady(page);
  };
  for (const size of SIZES) {
    const family = await seedHome(request);
    const tag = size.name;

    const his = await phone(browser, size, off);
    await signInThroughTheApp(his, family.phone, "Pa");
    await todayReady(his);
    await eachTab(his, "dad", tag);
    await his.getByTestId("open-feed").click();
    await settle(his);
    await snap(his, `dad-feed-${tag}`);
    await his.goto("./");
    await todayReady(his);
    await his.getByTestId("open-symptoms").click();
    await settle(his);
    await snap(his, `dad-symptoms-${tag}`);
    await his.goto("./");
    await todayReady(his);
    await his.getByTestId("write-reading").click();
    await expect(his.getByTestId("reading-photo")).toBeVisible();
    await his.getByTestId("photo-input").setInputFiles({ name: "cuff.png", mimeType: "image/png", buffer: placeholderPng("bp-cuff-2026-09-14") });
    await expect(his.getByTestId("review-card")).toBeVisible();
    await settle(his);
    await snap(his, `dad-review-card-${tag}`);
    await his.goto("./");
    await todayReady(his);
    await openMe(his);
    await his.getByTestId("me-emergency").click();
    await expect(his.getByTestId("emergency-screen")).toBeVisible();
    await settle(his);
    await snap(his, `dad-emergency-${tag}`);
    await his.goto("./");
    await todayReady(his);
    await his.getByTestId("not-well").click();
    await settle(his);
    await snap(his, `dad-not-well-${tag}`);
    await his.context().close();

    const hers = await phone(browser, size, off);
    await signInThroughTheApp(hers, family.meiPhone, "Mei");
    await hers.getByTestId("door-key").click();
    await todayReady(hers);
    await eachTab(hers, "chief", tag);
    await hers.getByTestId("open-feed").click();
    await settle(hers);
    await snap(hers, `chief-feed-${tag}`);
    await hers.context().close();

    const fresh = await phone(browser, size, off);
    await signInThroughTheApp(fresh, freshPhone("+659881"), "Pa");
    await fresh.getByTestId("door-for-me").click();
    await settle(fresh);
    await snap(fresh, `onboarding-agree-${tag}`);
    await fresh.getByTestId("agree").click();
    await settle(fresh);
    await snap(fresh, `onboarding-about-${tag}`);
    await fresh.context().close();
  }
});
