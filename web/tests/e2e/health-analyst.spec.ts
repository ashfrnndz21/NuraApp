import { expect, test, type Page } from "@playwright/test";
import { fixClock, seedOwner } from "./helpers";
import { seedHome } from "./homeSeed";
import { signInAs } from "./record-helpers";

/** Health and the Health Analyst, in the blueprint's own language (package 10,
 *  docs/design/experience-blueprint.html scenes `health`/`analyst`): the calm empty state a
 *  fresh profile actually sees, the real stream a report generates from, the quiet list of
 *  earlier reports, and the caregiver's own voice reading it. `health.spec.ts` already covers
 *  the readings, medicines and "Coming up" blocks; this file is the Health Analyst screen and
 *  the two defects package 10 fixed (the ring's "0 of 0", the console error on every fresh
 *  Health load). */

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  return errors;
}

test("a fresh owner's Health: the calm empty state, no \"0 of 0\", and no console error on load", async ({ page, request }) => {
  const errors = collectConsoleErrors(page);
  const ash = await seedOwner(request, "Ash", []);
  await signInAs(page, ash, "Ash");
  await page.getByTestId("tab-health").click();
  await expect(page.getByTestId("health-screen")).toBeVisible();

  // The ring: nothing to count yet, said calmly — never the ring with "0 of 0" in it.
  await expect(page.getByTestId("health-ring")).toHaveCount(0);
  const ringEmpty = page.getByTestId("health-ring-empty");
  await expect(ringEmpty).toBeVisible();
  await expect(ringEmpty).not.toHaveText("0 of 0");

  // The Health Analyst card: nothing generated yet, said plainly, never a blank space.
  await expect(page.getByTestId("insights-none")).toBeVisible();

  // `GET /profiles/{id}/insights` used to answer 404 on exactly this load (package 10 §2's
  // own defect); it now answers 200 with `null`, so the browser logs no failed request.
  await page.waitForFunction(() => document.querySelector("main")?.getAttribute("aria-busy") !== "true").catch(() => undefined);
  await page.waitForTimeout(300);
  expect(errors, errors.join("\n")).toEqual([]);
});

test("generate a report on demand: the real stream's stages, then the headline, then the sections", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();
  await page.getByTestId("insights-generate").click();

  const screen = page.getByTestId("insights-screen");
  await expect(screen).toBeVisible();
  await expect(screen.locator("h1")).toHaveText("Your week");

  // The busy state: the orb beside ONE status line — never an accumulating list — showing a
  // real stage the backend actually reported (`records`, `series`, `medicines`, `ledger` or
  // `coverage`, `test_analyst_api.py`'s own fixed order).
  const status = page.getByTestId("insights-status");
  await expect(status).toBeVisible();
  await expect(page.locator('[data-testid="insights-status"] ol, [data-testid="insights-status"] li')).toHaveCount(0);

  // The stream settles: the headline (its plain reading, `.sr-only`), then the report's own
  // sections, in the backend's fixed order, then the boundary line. Waiting for the report
  // itself (an auto-retrying assertion) rather than for the busy state's testid count to drop
  // to zero: that count is also zero before the busy state has ever mounted, so it cannot
  // itself tell "finished" from "not started yet".
  await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("insights-thinking")).toHaveCount(0);
  const headline = page.getByTestId("insights-headline");
  await expect(headline).toBeVisible();
  await expect(headline.locator(".sr-only")).not.toBeEmpty();

  const report = page.getByTestId("insights-report");
  await expect(report).toBeVisible();
  await expect(page.getByTestId("insights-section-what_changed")).toBeVisible();
  await expect(page.getByTestId("insights-section-questions_for_the_doctor")).toBeVisible();
  await expect(page.getByTestId("insights-boundary")).toBeVisible();

  // "Look again", not "Generate now", once a report is already on screen.
  await expect(page.getByTestId("insights-generate")).toHaveText("Look again");
});

test("open a past report from the quiet list", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();

  // Two reports, so there is a real "earlier" one to open.
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-thinking")).toBeVisible();
  await expect(page.getByTestId("insights-thinking")).toHaveCount(0, { timeout: 15_000 });

  const past = page.getByTestId("insights-past-list");
  await expect(past).toBeVisible();
  const rows = page.locator('[data-testid="insights-past-list"] [data-testid^="insights-past-"]');
  await expect(rows).toHaveCount(2);
  await rows.nth(1).click();
  await expect(page.getByTestId("insights-report")).toBeVisible();
  await expect(page.getByTestId("insights-section-what_changed")).toBeVisible();
});

test("her Health Analyst: Pa's report, in her own voice, never \"your\"", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, { phone: pa.meiPhone }, "Mei", true);
  await page.getByTestId("tab-health").click();
  await expect(page.getByTestId("health-screen").locator("h1")).toHaveText("Pa's health");
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-screen").locator("h1")).toHaveText("Pa's week");
  await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });

  const lines = await page.locator('[data-testid="insights-report"] p, [data-testid="insights-headline"] .sr-only').allTextContents();
  const aboutHer = lines.filter((line) => /\byour\b|\byou\b/i.test(line));
  expect(aboutHer, aboutHer.join("\n")).toEqual([]);
});

test("leaving the screen mid-stream aborts it: no error, no state update after unmount", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  const errors = collectConsoleErrors(page);
  await page.getByTestId("tab-health").click();
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-thinking")).toBeVisible();
  // Away before the stream settles — the tab bar, not a reload, so the same component
  // instance is the one being torn down.
  await page.getByTestId("tab-home").click();
  await expect(page.getByTestId("today-screen")).toBeVisible();
  await page.waitForTimeout(1_000);
  expect(errors, errors.join("\n")).toEqual([]);
  // Coming back finds a screen that still works, not one wedged mid-stream.
  await page.getByTestId("tab-health").click();
  await expect(page.getByTestId("health-screen")).toBeVisible();
});

test("a network failure mid-stream: what already arrived stays, and there is a way to try again", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();
  await page.route("**/insights/stream", (route) => route.abort("failed"));
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-screen")).toBeVisible();
  await expect(page.getByTestId("notice")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("insights-generate")).toBeVisible();
  await expect(page.getByTestId("insights-generate")).toHaveText("Try again");
});

// --- geometry: nothing under the tab bar, the primary button fully visible, no label crossing
// its own value, at three breakpoints (package 10) -------------------------------------------

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}
function boxesIntersect(a: Box, b: Box): boolean {
  return !(a.x + a.width <= b.x || b.x + b.width <= a.x || a.y + a.height <= b.y || b.y + b.height <= a.y);
}

for (const [label, size] of [
  ["390x844", { width: 390, height: 844 }],
  ["360x640", { width: 360, height: 640 }],
  ["1280x900", { width: 1280, height: 900 }],
] as const) {
  test(`Health's geometry holds at ${label}: nothing under the tab bar, no label crossing its value`, async ({ page, request }) => {
    await page.setViewportSize(size);
    const pa = await seedHome(request);
    await signInAs(page, pa, "Pa");
    await page.getByTestId("tab-health").click();
    await expect(page.getByTestId("health-screen")).toBeVisible();
    // Real seeded data (`seedHome`'s blood pressure book): wait for the row itself, not merely
    // its (possibly still-loading) container, before counting metric rows below it.
    await expect(page.getByTestId("reading-bp")).toBeVisible();

    const tabBar = page.locator(".tabbar").first();
    const tabBarBox = await tabBar.boundingBox().catch(() => null);
    const rows = page.locator(".metric-row");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const row = rows.nth(i);
      const labelBox = await row.locator(".metric-label").boundingBox();
      const valueBox = await row.locator(".metric-value").boundingBox();
      if (!labelBox || !valueBox) continue;
      expect(boxesIntersect(labelBox, valueBox), `row ${i} at ${label}: label crosses value`).toBe(false);
      if (tabBarBox) {
        expect(labelBox.y + labelBox.height, `row ${i} at ${label}: under the tab bar`).toBeLessThanOrEqual(tabBarBox.y + 1);
      }
    }
  });

  test(`the Health Analyst's primary button is fully visible at ${label}`, async ({ page, request }) => {
    await page.setViewportSize(size);
    const pa = await seedHome(request);
    await signInAs(page, pa, "Pa");
    await page.getByTestId("tab-health").click();
    await page.getByTestId("insights-generate").click();
    // Wait for the report itself to be there (an auto-retrying assertion), never a one-shot
    // "the busy state is gone" check: `toHaveCount(0)` on a testid that has not mounted yet
    // resolves true instantly, before the stream has even begun, which is not "finished".
    await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });
    const button = page.getByTestId("insights-generate");
    await expect(button).toBeVisible();
    await expect
      .poll(async () => (await button.boundingBox()) !== null, { timeout: 5_000 })
      .toBe(true);
    const box = await button.boundingBox();
    // Above 600px wide the app sits inside a 390px device frame (`.phone-frame`, the brief's
    // own rule); below it, full-bleed, and the frame element itself is the plain page.
    const frame = page.locator(".phone-frame");
    const frameBox = (await frame.count()) > 0 ? await frame.boundingBox() : null;
    if (!box) throw new Error("the button did not lay out");
    if (frameBox) {
      expect(box.x, `${label}: the button starts left of the frame`).toBeGreaterThanOrEqual(frameBox.x - 1);
      expect(box.x + box.width, `${label}: the button runs past the frame's right edge`).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
    }
    expect(box.y, `${label}: the button starts above the viewport`).toBeGreaterThanOrEqual(0);
  });
}
