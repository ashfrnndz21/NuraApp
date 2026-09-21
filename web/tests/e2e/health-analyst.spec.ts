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

  // The orb sits beside the finished headline (not thinking) — the same treatment Ask gives a
  // settled turn (package 10 review #3).
  await expect(page.getByTestId("insights-orb-done")).toBeVisible();

  // "What Nura looked at" collapses the five real stages into ONE quiet, expandable line —
  // never five chips left standing after the report is assembled (package 10 review #1).
  const lookedAt = page.getByTestId("insights-looked-at");
  await expect(lookedAt).toBeVisible();
  await expect(lookedAt).toContainText("What Nura looked at:");
  await expect(lookedAt.locator(".chip-row")).toHaveCount(0);
  await expect(lookedAt).not.toHaveAttribute("open", "");

  const report = page.getByTestId("insights-report");
  await expect(report).toBeVisible();
  await expect(page.getByTestId("insights-section-what_changed")).toBeVisible();
  await expect(page.getByTestId("insights-section-questions_for_the_doctor")).toBeVisible();
  await expect(page.getByTestId("insights-boundary")).toBeVisible();

  // "Say it once": the headline's own sentence is the one insight promoted out of its
  // section, so it is not repeated as the first item under "What changed" (package 10 review
  // #2).
  const headlineText = (await headline.locator(".sr-only").textContent())?.trim() ?? "";
  expect(headlineText.length).toBeGreaterThan(0);
  const whatChangedText = await page.getByTestId("insights-section-what_changed").innerText();
  expect(whatChangedText.split(headlineText).length - 1, `"${headlineText}" repeated in What changed:\n${whatChangedText}`).toBeLessThanOrEqual(1);

  // "Look again", not "Generate now", once a report is already on screen.
  await expect(page.getByTestId("insights-generate")).toHaveText("Look again");
});

test("'Ask … this' names a real doctor, never the raw role word", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });

  const askButtons = page.getByTestId("insight-ask");
  const count = await askButtons.count();
  const texts = await askButtons.allTextContents();
  for (const one of texts) {
    expect(one, `broken "Ask … this" wording: "${one}"`).not.toMatch(/Ask (doctor|pharmacist|nobody) this/);
  }
  // seedHome's own next visit names a real doctor (`homeSeed.ts`, "Dr Tan" — the same one
  // health.spec.ts's "Coming up" tile already asserts): at least one ask names him by name
  // rather than falling back to the plain word, when the report has a doctor-ask finding at
  // all.
  if (count > 0) expect(texts.some((one) => one.includes("Dr Tan") || one.includes("your pharmacist"))).toBe(true);
});

test("'Why' is a real disclosure: closed by default, a chevron, opens on tap", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();
  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });

  const why = page.getByTestId("insight-why").first();
  await expect(why).toBeVisible();
  await expect(why).not.toHaveAttribute("open", "");
  await expect(why.locator("svg")).toBeVisible();
  await why.locator("summary").click();
  await expect(why).toHaveAttribute("open", "");
  await expect(page.getByTestId("insight-why-body").first()).toBeVisible();
});

// --- package 10 review #6: 12px between a section heading and its card, 24px between one
// section and the next, on both screens ---------------------------------------------------------

async function headingCardGaps(page: import("@playwright/test").Page, screenTestId: string): Promise<number[]> {
  return page.locator(`main[data-testid="${screenTestId}"] .section-head`).evaluateAll((heads) =>
    heads
      .map((head) => {
        const next = head.nextElementSibling;
        if (!next) return null;
        const a = head.getBoundingClientRect();
        const b = next.getBoundingClientRect();
        return b.top - a.bottom;
      })
      .filter((gap): gap is number => gap !== null),
  );
}

test("every section heading sits at least 8px above its card, on Health and the Health Analyst", async ({ page, request }) => {
  const pa = await seedHome(request);
  await signInAs(page, pa, "Pa");
  await page.getByTestId("tab-health").click();
  await expect(page.getByTestId("reading-bp")).toBeVisible();
  await page.waitForTimeout(1_700); // the reveal stagger (up to ~7 sections, 140ms apart) and its 550ms transition settle
  const healthGaps = await headingCardGaps(page, "health-screen");
  expect(healthGaps.length).toBeGreaterThan(0);
  for (const gap of healthGaps) expect(gap, `Health: a heading sits ${gap}px above its card`).toBeGreaterThanOrEqual(8);

  await page.getByTestId("insights-generate").click();
  await expect(page.getByTestId("insights-report")).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(1_700);
  const analystGaps = await headingCardGaps(page, "insights-screen");
  expect(analystGaps.length).toBeGreaterThan(0);
  for (const gap of analystGaps) expect(gap, `Health Analyst: a heading sits ${gap}px above its card`).toBeGreaterThanOrEqual(8);
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

  const lines = await page
    .locator('[data-testid="insights-report"] p, [data-testid="insights-headline"] .sr-only, [data-testid="insight-ask"], [data-testid="insights-looked-at"]')
    .allTextContents();
  const aboutHer = lines.filter((line) => /\byour\b|\byou\b/i.test(line));
  expect(aboutHer, aboutHer.join("\n")).toEqual([]);

  // Named doctor or not, an ask button never reads the broken "Ask doctor this" — and in her
  // voice the fallback is "Pa's doctor", never "your doctor" (package 10 review #4).
  const askTexts = await page.getByTestId("insight-ask").allTextContents();
  for (const one of askTexts) expect(one, `broken "Ask … this" wording: "${one}"`).not.toMatch(/Ask (doctor|pharmacist|nobody) this/);
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
  test(`Health's geometry holds at ${label}: no label crossing its value, nothing left under the tab bar once scrolled to`, async ({ page, request }) => {
    await page.setViewportSize(size);
    const pa = await seedHome(request);
    await signInAs(page, pa, "Pa");
    await page.getByTestId("tab-health").click();
    await expect(page.getByTestId("health-screen")).toBeVisible();
    // Real seeded data (`seedHome`'s blood pressure book): wait for the row itself, not merely
    // its (possibly still-loading) container, before counting metric rows below it — and for
    // the reveal stagger and its own transition to fully settle, so a mid-transition (still
    // blurred, still translating) frame is never what geometry is measured against.
    await expect(page.getByTestId("reading-bp")).toBeVisible();
    await page.waitForTimeout(1_700);

    const tabBar = page.locator(".tabbar").first();
    const tabBarBox = await tabBar.boundingBox().catch(() => null);
    const rows = page.locator(".metric-row");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const row = rows.nth(i);
      // A screen this full does not fit above the fold on a short phone without scrolling —
      // scrolled to (never simply "on the first screenful"), a row must still never end up
      // physically covered by the docked tab bar.
      await row.scrollIntoViewIfNeeded();
      const labelBox = await row.locator(".metric-label").boundingBox();
      const valueBox = await row.locator(".metric-value").boundingBox();
      if (!labelBox || !valueBox) continue;
      expect(boxesIntersect(labelBox, valueBox), `row ${i} at ${label}: label crosses value`).toBe(false);
      if (tabBarBox) {
        expect(labelBox.y + labelBox.height, `row ${i} at ${label}: under the tab bar once scrolled to`).toBeLessThanOrEqual(tabBarBox.y + 1);
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
