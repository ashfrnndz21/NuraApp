import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** `#/blueprint-kit` (P1 of the redesign, docs/design/experience-blueprint.html): the review
 *  gallery of the dusk-glass kit (`web/src/ui/kit`). Never linked from the real app; reached only
 *  when this deployment answers `dev` or `demo` on `GET /api/deployment` and the hash is set.
 *  Structural and behavioural assertions only — no pixel snapshot (mac vs Linux font rendering
 *  differs), matching how the rest of this suite checks the design pass. The gallery does not
 *  need offline support, and a service worker across runs of this file was observed serving a
 *  stale build once already cached — blocked here so every run measures the page this run's
 *  server actually served. */
test.use({ serviceWorkers: "block" });

async function openGallery(page: Page): Promise<void> {
  await page.route("**/api/deployment", (route) => route.fulfill({ json: { region: "SG", demo: false, dev: true, push_key: null } }));
  await page.goto("./#/blueprint-kit");
  await expect(page.getByTestId("blueprint-kit-gallery")).toBeVisible();
  // Every RevealGroup's own stagger has finished, so a check right after (axe, contrast) sees
  // the settled page rather than a frame mid-transition.
  await page.waitForTimeout(900);
}

// Deliberately its own test, with no shared `beforeEach`: it needs a deployment that is neither
// demo nor dev from the very first navigation, and `learnDeployment()` remembers the last answer
// in IndexedDB (`device.demo`) — sharing a `beforeEach` that first opens the gallery as a dev
// deployment would leave that remembered `true` behind for this test's own fresh navigation.
test("is not reachable when the deployment is neither demo nor dev", async ({ page }) => {
  await page.route("**/api/deployment", (route) => route.fulfill({ json: { region: "SG", demo: false, dev: false, push_key: null } }));
  await page.goto("./#/blueprint-kit");
  // The real app renders instead — the welcome screen or sign-in, never the gallery.
  await expect(page.getByTestId("blueprint-kit-gallery")).toHaveCount(0);
});

test("StatusLine is a single element whose text changes in place, never a stack of lines", async ({ page }) => {
  await openGallery(page);
  const status = page.getByTestId("gallery-status");
  await expect(status).toHaveCount(1);
  await expect(status).toHaveAttribute("aria-live", "polite");
  const first = (await status.textContent())?.trim();
  await page.getByTestId("gallery-status-next").click();
  // Still exactly one status line — it changed in place, it did not stack a second one.
  await expect(status).toHaveCount(1);
  await expect
    .poll(async () => (await status.textContent())?.trim())
    .not.toBe(first);
});

test("SoftText: every word is in the DOM, and streaming only adds new words rather than replacing the line", async ({ page }) => {
  await openGallery(page);
  const headline = page.getByTestId("gallery-softtext");
  await expect(headline).toBeVisible();
  const firstWordCount = await headline.locator(".soft-word").count();
  expect(firstWordCount).toBeGreaterThan(0);
  await page.getByTestId("gallery-softtext-next").click();
  await expect
    .poll(async () => headline.locator(".soft-word").count())
    .toBeGreaterThan(firstWordCount);
  // The full sentence is always readable, for a screen reader, as one real (not aria-label)
  // visually-hidden text node — axe's aria-prohibited-attr refuses aria-label on a plain <p>.
  await expect(headline.locator(".sr-only")).toHaveText(/Your health, in plain words\.|Your$|Your health,$|Your health, in$|Your health, in plain$/);
});

test("the accent word is styled in the italic serif face, never a whole heading", async ({ page }) => {
  await openGallery(page);
  // The sample conversation's headline carries its accent word already, with no streaming
  // needed to reach it.
  const accent = page.getByTestId("gallery-sample-headline").locator(".accent");
  await expect(accent).toHaveCount(1);
  await expect(accent).toHaveText("paper.");
  const family = await accent.evaluate((el) => getComputedStyle(el).fontFamily);
  expect(family).toContain("Instrument Serif");
  const headlineFamily = await page.getByTestId("gallery-sample-headline").evaluate((el) => getComputedStyle(el).fontFamily);
  expect(headlineFamily).toContain("Figtree");
});

test("the sheet opens, and its button goes through three real states", async ({ page }) => {
  await openGallery(page);
  await page.getByTestId("gallery-open-sheet").click();
  const sheet = page.getByTestId("gallery-sample-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[role="dialog"]')).toBeVisible();

  const cta = page.getByTestId("action-sheet-cta");
  await expect(cta).toHaveText("Add to my questions");
  await cta.click();
  await expect(cta).toHaveText("Adding…");
  await expect(cta).toBeDisabled();
  await expect(cta).toHaveText("Added", { timeout: 5000 });
  await expect(cta.locator("svg")).toBeVisible();

  // Escape closes it.
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});

test("Not now and the scrim both close the sheet", async ({ page }) => {
  await openGallery(page);
  await page.getByTestId("gallery-open-sheet").click();
  await expect(page.getByTestId("gallery-sample-sheet")).toBeVisible();
  await page.getByTestId("action-sheet-not-now").click();
  await expect(page.getByTestId("gallery-sample-sheet")).toHaveCount(0);
});

test("reduced motion: every word, every reveal and the status line are simply there — no animation runs", async ({ page }) => {
  // Set before the first navigation: the CSS media query must already match on first paint,
  // not only after a later reload.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openGallery(page);

  // No element on the page carries a running keyframe animation (the orb's spin, the status
  // line's sweep) — the global reduced-motion rule (base.css) turns every one off.
  const animated = await page.evaluate(() =>
    Array.from(document.querySelectorAll("*")).filter((el) => getComputedStyle(el).animationName !== "none").length,
  );
  expect(animated).toBe(0);

  // Every word in the headline is already visible (opacity 1, no blur) — no per-word delay.
  const opacities = await page.getByTestId("gallery-softtext").locator(".soft-word").evaluateAll((nodes) => nodes.map((n) => getComputedStyle(n).opacity));
  for (const opacity of opacities) expect(opacity).toBe("1");

  const reveals = await page.getByTestId("gallery-reveal-group").locator(".reveal-item").evaluateAll((nodes) => nodes.map((n) => getComputedStyle(n).opacity));
  for (const opacity of reveals) expect(opacity).toBe("1");
});

test("axe: no serious or critical finding on the gallery", async ({ page }) => {
  await openGallery(page);
  // The sheet open too, so its focus-trapped dialog is included in the same audit.
  await page.getByTestId("gallery-open-sheet").click();
  await expect(page.getByTestId("gallery-sample-sheet")).toBeVisible();
  await page.waitForTimeout(700);
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((each) => each.impact === "serious" || each.impact === "critical");
  expect(serious.map((each) => `${each.id} (${each.impact}): ${each.nodes.map((node) => node.target.join(" ")).slice(0, 3).join(" | ")}`)).toEqual([]);
});

test.describe("the phone frame (owner's scope change 2026-09-21)", () => {
  test("above 600px, the gallery sits inside the same 390px frame as the rest of the app", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openGallery(page);
    const frame = page.locator("#phone-frame");
    await expect(frame).toBeVisible();
    const frameBox = (await frame.boundingBox())!;
    expect(Math.round(frameBox.width)).toBe(390);
    const galleryBox = (await page.getByTestId("blueprint-kit-gallery").boundingBox())!;
    expect(galleryBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
    expect(galleryBox.x + galleryBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
  });

  test("a sheet opened above 600px lies inside the frame, not the full browser window", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openGallery(page);
    const frame = page.locator("#phone-frame");
    const frameBox = (await frame.boundingBox())!;
    await page.getByTestId("gallery-open-sheet").click();
    const sheetBox = (await page.getByTestId("gallery-sample-sheet").locator('[role="dialog"]').boundingBox())!;
    expect(sheetBox.x).toBeGreaterThanOrEqual(frameBox.x - 1);
    expect(sheetBox.x + sheetBox.width).toBeLessThanOrEqual(frameBox.x + frameBox.width + 1);
    expect(sheetBox.y).toBeGreaterThanOrEqual(frameBox.y - 1);
    expect(sheetBox.y + sheetBox.height).toBeLessThanOrEqual(frameBox.y + frameBox.height + 1);
  });
});
