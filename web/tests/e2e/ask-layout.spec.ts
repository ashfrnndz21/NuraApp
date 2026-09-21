import { expect, test, type Page } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { backendClock, fixClock, seedFeed, signInThroughTheApp, todayReady } from "./helpers";

/** P1 checkpoint 4, the layout fix: geometry, not words — `feed.spec.ts` and `family.spec.ts`
 *  already prove the streamed answer is real and the words are right; this proves the thread
 *  scrolls where it should and the composer never hides what it just said. Two viewports, the
 *  same two the app runs at (docs/design/experience-blueprint.html's own breakpoint): a phone
 *  (390x844, full-bleed) and a wide screen (1280x900, the phone frame centred on the page). */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)}): let Playwright start it, or start make dev with NURA_FROZEN_CLOCK`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function openAsk(page: Page): Promise<void> {
  await page.getByTestId("home-ask-open").click();
  await expect(page.getByTestId("ask-screen")).toBeVisible();
}

async function askAndFinish(page: Page, question: string): Promise<void> {
  await page.getByLabel("Your question").fill(question);
  await page.getByTestId("ask-send").click();
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
}

for (const viewport of [
  { width: 390, height: 844, name: "390x844" },
  { width: 1280, height: 900, name: "1280x900" },
] as const) {
  test(`Ask's thread and composer, ${viewport.name}: a two-turn conversation, nothing hidden`, async ({ page, request }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const pa = await seedFeed(request);
    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    await openAsk(page);

    await askAndFinish(page, "What was my blood pressure, and how long ago was that?");
    const composer = page.getByTestId("ask-composer");
    const tabbar = page.locator("nav.tabbar");
    await expect(composer).toBeVisible();
    await expect(tabbar).toBeVisible();
    const composerAfterTurn1 = (await composer.boundingBox())!;

    await askAndFinish(page, "When is my next visit?");
    await expect(page.getByTestId("ask-earlier-turns")).toBeVisible();

    // (a) The composer's bottom edge is at or above the tab bar's top edge, and it is visible —
    // docked above the tab bar (`Shell`'s `bottomBar`), never under it.
    const composerBox = (await composer.boundingBox())!;
    const tabbarBox = (await tabbar.boundingBox())!;
    expect(composerBox.y + composerBox.height).toBeLessThanOrEqual(tabbarBox.y + 1);

    // (b) The last answer line's bottom is at or above the composer's top — nothing of the
    // newest answer sits under the docked composer.
    const lastLine = page.getByTestId("answer-line").last();
    const lastLineBox = (await lastLine.boundingBox())!;
    expect(lastLineBox.y + lastLineBox.height).toBeLessThanOrEqual(composerBox.y + 1);

    // (c) Every question bubble — the earlier turn and the live one alike — is right-aligned:
    // its right edge within 24px of the thread's own right edge (the defect this replaces had
    // the earlier question full-width and left-started, `align-self` never applying outside a
    // flex column).
    const thread = page.getByTestId("ask-thread");
    const threadBox = (await thread.boundingBox())!;
    const threadRight = threadBox.x + threadBox.width;
    const questionBubbles = await page.locator('[data-testid="ask-question"], [data-testid="ask-earlier-question"]').all();
    expect(questionBubbles.length).toBeGreaterThanOrEqual(2);
    for (const bubble of questionBubbles) {
      const box = (await bubble.boundingBox())!;
      expect(threadRight - (box.x + box.width)).toBeLessThanOrEqual(24);
    }

    // (d) The composer stays put in the viewport once the thread has grown and scrolled: it is
    // docked in the shell's own flex flow (never `position: fixed` over content), so asking a
    // second question — which makes the thread taller and scrolls it — never moves the composer.
    expect(Math.abs(composerBox.y - composerAfterTurn1.y)).toBeLessThanOrEqual(1);
  });
}
