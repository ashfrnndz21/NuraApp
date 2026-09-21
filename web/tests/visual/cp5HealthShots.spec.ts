import { mkdirSync } from "node:fs";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import { fixClock, seedOwner, signInThroughTheApp } from "../e2e/helpers";
import { seedHome } from "../e2e/homeSeed";

/** Health and the Health Analyst (package 10), against the blueprint's `health`/`analyst`
 *  scenes — not a gate, pictures for the operator to look at, into
 *  `/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-health/`
 *  by default (`NURA_DESIGN_SHOTS` overrides it, the same convention `shots.spec.ts` keeps). */

const OUT = process.env.NURA_DESIGN_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-health";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 15_000 });

const SIZES = [
  { name: "390x844", width: 390, height: 844 },
  { name: "1280x900", width: 1280, height: 900 },
] as const;

async function phone(browser: Browser, size: (typeof SIZES)[number]): Promise<Page> {
  const context = await browser.newContext({
    baseURL: BASE_URL,
    viewport: { width: size.width, height: size.height },
    deviceScaleFactor: 2,
    isMobile: size.width < 600,
    hasTouch: size.width < 600,
    timezoneId: "Asia/Singapore",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  await fixClock(page);
  return page;
}

async function snap(page: Page, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${OUT}/${name}.png`, animations: "disabled" });
}

/** The one capture that means to catch a CSS transition still in flight (the report's own
 *  sections assembling in with `RevealGroup`, headline already up): `animations: "disabled"`
 *  fast-forwards every transition to its end state, which is right for every other shot here
 *  (stable, never flaky on a slow run) and wrong for exactly this one. */
async function snapMidTransition(page: Page, name: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

test("Health and the Health Analyst, at two sizes", async ({ browser, request }) => {
  for (const size of SIZES) {
    // --- Health top and scrolled, Pa's own seeded record ---
    const pa = await seedHome(request);
    const his = await phone(browser, size);
    await signInThroughTheApp(his, pa.phone, "Pa");
    await his.getByTestId("tab-health").click();
    await expect(his.getByTestId("health-screen")).toBeVisible();
    await expect(his.getByTestId("insights-none")).toBeVisible();
    await expect(his.getByTestId("health-ring")).toBeVisible();
    await expect(his.getByTestId("reading-bp")).toBeVisible();
    await expect(his.getByTestId("health-more")).toBeVisible();
    await snap(his, `health-top-${size.name}`);

    const scroller = his.getByTestId("shell-scroll");
    await scroller.hover();
    await his.mouse.wheel(0, 900);
    await his.waitForTimeout(200);
    await snap(his, `health-scrolled-${size.name}`);
    await his.context().close();

    // --- fresh owner: the calm empty state, no "0 of 0" ---
    const ash = await seedOwner(request, "Ash", []);
    const fresh = await phone(browser, size);
    await signInThroughTheApp(fresh, ash.phone, "Ash");
    await fresh.getByTestId("tab-health").click();
    await expect(fresh.getByTestId("health-ring-empty")).toBeVisible();
    await expect(fresh.getByTestId("insights-none")).toBeVisible();
    await snap(fresh, `health-fresh-owner-${size.name}`);
    await fresh.context().close();

    // --- the Health Analyst: mid-thinking, mid-headline, fully assembled, past reports ---
    const analystOwner = await seedHome(request);
    const analyst = await phone(browser, size);
    await signInThroughTheApp(analyst, analystOwner.phone, "Pa");
    await analyst.getByTestId("tab-health").click();

    // The real stream (five fixture reads) settles in well under a second — too fast to catch
    // "mid-thinking" or "mid-headline" as they really render without slowing the network down.
    // CDP throttling spreads the SAME real bytes out over real wall-clock time (never a fake
    // delay the app itself adds, never invented content): the stages and the report are still
    // exactly what the backend sent, only arriving the way a slower connection would carry them.
    const cdp = await analyst.context().newCDPSession(analyst);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 60, downloadThroughput: 6_000, uploadThroughput: -1 });

    await analyst.getByTestId("insights-generate").click();
    await expect(analyst.getByTestId("insights-thinking")).toBeVisible();
    await analyst.waitForTimeout(500);
    // A best-effort capture: the throttle above usually spreads the five real `step` events
    // and the report out enough to land here mid-stream (a real stage's label replacing the
    // starting line); on a run where the whole fixture stream still lands inside the 500ms
    // window, this frame is simply the same as `analyst-assembled` instead — never a wrong or
    // invented frame, only sometimes not a distinct one.
    await snap(analyst, `analyst-mid-thinking-${size.name}`);

    await expect(analyst.getByTestId("insights-headline")).toBeVisible({ timeout: 45_000 });
    await snapMidTransition(analyst, `analyst-mid-headline-${size.name}`);

    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await expect(analyst.getByTestId("insights-boundary")).toBeVisible({ timeout: 30_000 });
    await analyst.waitForTimeout(400); // the reveal stagger settles, nothing still mid-transition
    await snap(analyst, `analyst-assembled-${size.name}`);

    // A second report, so "Earlier reports" has something real in it.
    await analyst.getByTestId("insights-generate").click();
    await expect(analyst.getByTestId("insights-thinking")).toBeVisible();
    await expect(analyst.getByTestId("insights-thinking")).toHaveCount(0, { timeout: 15_000 });
    await expect(analyst.getByTestId("insights-past-list")).toBeVisible();
    await analyst.getByTestId("insights-past-list").scrollIntoViewIfNeeded();
    await analyst.waitForTimeout(150);
    await snap(analyst, `analyst-past-reports-${size.name}`);
    await analyst.context().close();

    // --- Mei's Health: his readings and his report, said about him by name ---
    const hers = await phone(browser, size);
    await signInThroughTheApp(hers, analystOwner.meiPhone, "Mei");
    await hers.getByTestId("door-key").click();
    await hers.getByTestId("tab-health").click();
    await expect(hers.getByTestId("health-screen").locator("h1")).toHaveText("Pa's health");
    await expect(hers.getByTestId("health-ring")).toBeVisible();
    await expect(hers.getByTestId("reading-bp")).toBeVisible();
    await snap(hers, `health-mei-${size.name}`);
    await hers.context().close();
  }
});
