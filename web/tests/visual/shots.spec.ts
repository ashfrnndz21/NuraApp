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

/** Stage 2 (D1): every restyled screen, in both densities, at both sizes, with the banner off.
 *  One tab set now (the reset), so the walk is the same for him and for her: each tab, each
 *  place in his Record, each part of Family, the switcher, the feed, the day's four screens,
 *  the emergency card and the review card. Each is taken twice — what the phone shows first,
 *  and the whole page with its tab bar at the end ("-full"). */
test("every restyled screen: the tabs, the Record's places, Family's parts, the switcher, the day, the cards", async ({ browser, request }) => {
  test.setTimeout(1_800_000);
  const off = { on: false };
  const settle = async (page: Page) => {
    await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    await page.evaluate(() => document.fonts.ready);
  };

  /** Every tab in the bar, by the word on it, back to the first when it is done. */
  const eachTab = async (page: Page, who: string, tag: string) => {
    const tabs = page.locator("nav.tabbar button");
    const count = await tabs.count();
    for (let index = 1; index < count; index += 1) {
      const name = ((await tabs.nth(index).innerText()).trim().toLowerCase() || `tab${index}`).replace(/\W+/g, "-");
      await tabs.nth(index).click();
      await settle(page);
      await snap(page, `${who}-tab-${name}-${tag}`);
    }
    await tabs.nth(0).click();
    await todayReady(page);
  };

  /** Each place in his Record: the Papers tab, then the place — the two taps the design allows. */
  const eachPlace = async (page: Page, who: string, tag: string) => {
    for (const entry of ["medicines", "papers", "routine", "timeline", "trends", "providers", "changes"]) {
      await page.getByTestId("tab-records").click();
      const row = page.getByTestId(`record-${entry}`);
      if (!(await row.isVisible().catch(() => false))) continue;
      await row.click();
      await settle(page);
      await snap(page, `${who}-record-${entry}-${tag}`);
    }
  };

  /** Each part of Family the key opens. */
  const eachPart = async (page: Page, who: string, tag: string) => {
    const parts = ["keys", "trail", "roster", "thread", "messages", "metrics", "calendar", "deliveries", "settings", "documents", "consents", "onlyMe"];
    for (const part of parts) {
      await page.getByTestId("tab-family").click();
      const way = page.getByTestId(`open-${part}`);
      if (!(await way.isVisible().catch(() => false))) continue;
      await way.click();
      await settle(page);
      await snap(page, `${who}-family-${part}-${tag}`);
    }
  };

  for (const size of SIZES) {
    const family = await seedHome(request);
    const tag = size.name;

    // --- his phone -------------------------------------------------------------------------
    const his = await phone(browser, size, off);
    await signInThroughTheApp(his, family.phone, "Pa");
    await todayReady(his);
    await eachTab(his, "dad", tag);
    await eachPlace(his, "dad", tag);
    await eachPart(his, "dad", tag);

    // The switcher: whose papers are open, and the way to every other set.
    await his.getByTestId("tab-today").click();
    await todayReady(his);
    await his.getByTestId("whose").click();
    await settle(his);
    await his.screenshot({ path: `${OUT}/dad-switcher-${tag}.png`, animations: "disabled" });
    await his.getByTestId("sheet-close").click();

    await his.getByTestId("open-feed").click();
    await settle(his);
    await snap(his, `dad-feed-${tag}`);

    // The day's four screens: the pill, what to do now, the symptom log, a feeling.
    await his.getByTestId("tab-today").click();
    await todayReady(his);
    await his.getByTestId("open-symptoms").click();
    await settle(his);
    await snap(his, `dad-symptoms-${tag}`);
    await his.getByTestId("tab-today").click();
    await todayReady(his);
    await his.getByTestId("not-well").click();
    await settle(his);
    await snap(his, `dad-not-well-${tag}`);

    // The blood pressure typed or photographed, and its review card.
    await his.getByTestId("tab-today").click();
    await todayReady(his);
    await his.getByTestId("write-reading").click();
    await expect(his.getByTestId("reading-photo")).toBeVisible();
    await settle(his);
    await snap(his, `dad-reading-${tag}`);
    await his.getByTestId("photo-input").setInputFiles({ name: "cuff.png", mimeType: "image/png", buffer: placeholderPng("bp-cuff-2026-09-14") });
    await expect(his.getByTestId("review-card")).toBeVisible();
    await settle(his);
    await snap(his, `dad-review-card-${tag}`);

    // The emergency card, from Me.
    await his.goto("./");
    await todayReady(his);
    await openMe(his);
    await his.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
    await his.getByTestId("me-emergency").click();
    await expect(his.getByTestId("emergency-screen")).toBeVisible();
    await settle(his);
    await snap(his, `dad-emergency-${tag}`);
    await his.context().close();

    // --- her phone -------------------------------------------------------------------------
    const hers = await phone(browser, size, off);
    await signInThroughTheApp(hers, family.meiPhone, "Mei");
    await hers.getByTestId("door-key").click();
    await todayReady(hers);
    await eachTab(hers, "chief", tag);
    await eachPlace(hers, "chief", tag);
    await eachPart(hers, "chief", tag);

    await hers.getByTestId("tab-today").click();
    await todayReady(hers);
    await hers.getByTestId("whose").click();
    await settle(hers);
    await hers.screenshot({ path: `${OUT}/chief-switcher-${tag}.png`, animations: "disabled" });
    await hers.getByTestId("sheet-close").click();

    await hers.getByTestId("open-feed").click();
    await settle(hers);
    await snap(hers, `chief-feed-${tag}`);
    await hers.context().close();

    // --- onboarding and the doors, on a phone that has never been used ----------------------
    const fresh = await phone(browser, size, off);
    await signInThroughTheApp(fresh, freshPhone("+659881"), "Pa");
    await settle(fresh);
    await snap(fresh, `doors-${tag}`);
    await fresh.getByTestId("door-for-me").click();
    await settle(fresh);
    await snap(fresh, `onboarding-agree-${tag}`);
    await fresh.getByTestId("agree").click();
    await expect(fresh.getByLabel("The name Nura uses")).toBeVisible();
    await settle(fresh);
    await snap(fresh, `onboarding-about-${tag}`);
    await fresh.context().close();
  }
});
