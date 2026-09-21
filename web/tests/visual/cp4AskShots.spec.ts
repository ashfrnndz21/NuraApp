import { mkdirSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { todayReady } from "../e2e/helpers";

/** P1 (checkpoint 4, "Ask feels like a natural, streamed conversation"): screen captures of
 *  the real app, against a deployment seeded with `NURA_DEMO_SEED=1` (`docs/deploy-demo.md`),
 *  signed in through the Welcome screen's "Try it as Pa" — never a synthetic Playwright fixture
 *  family, and never a faked delay inside the app itself. The rule-based asker only (never
 *  `NURA_ASKER=claude`, never a real model, never an API key): its trace and its sentences are
 *  the real backend's own words, streamed for real.
 *
 *  Not a gate — `npx playwright test -c playwright.visual.config.ts tests/visual/
 *  cp4AskShots.spec.ts` writes pictures for a person to look at, into `NURA_ASK_SHOTS`
 *  (default: this checkpoint's own folder under the scratchpad).
 *
 *  "Mid-thinking" is reliable and never faked: the orb and the one status line are already on
 *  screen the instant `send` sets `busy`, well before the network call resolves, so a
 *  screenshot fired right after the click (not awaited on the response) genuinely lands there
 *  — `_delayAskStream` below only holds the real response a little longer so that window is
 *  wide enough to always catch, the same test-only network hold `docs/design/experience-
 *  blueprint.html`'s own reference build never needed but this checkpoint's brief explicitly
 *  allows ("hold/chunk the SSE if needed — test tooling only, nothing faked in the app"). The
 *  content itself — every step, every sentence, the finished answer — is the real backend's,
 *  read back byte for byte from `route.fetch()`; only its arrival is held. "Mid-stream" (the
 *  first sentence visible, the second still arriving) is best-effort: it polls for the DOM to
 *  show exactly one `answer-line` and shoots the instant it does, which is real, unforced
 *  timing between two real `answer_sentence` events — on a very fast local backend with a
 *  one-sentence answer this window can be too narrow to land inside, in which case the shot
 *  simply shows the finished answer instead (never a fabricated in-between frame). */

const OUT = process.env.NURA_ASK_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp4-ask";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

/** Holds the real `ask/stream` (or a named thread's `turns/stream`) response for `ms` before
 *  letting the browser see it, so "mid-thinking" has a wide, reliable window — the request
 *  still reaches the real backend and the response is its own, unedited; this only delays
 *  when the already-finished response is handed to the page. */
async function delayAskStream(page: Page, ms: number): Promise<void> {
  await page.route(/\/(ask|turns)\/stream$/, async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, ms));
    await route.fulfill({ response });
  });
}

async function tryItAsPa(page: Page): Promise<void> {
  await page.goto("./");
  await expect(page.getByTestId("welcome-screen")).toBeVisible();
  const button = page.getByTestId("welcome-try-pa");
  await expect(button).toBeVisible({ timeout: 15_000 });
  await button.click();
  await expect(page.getByTestId("welcome-screen")).toHaveCount(0, { timeout: 15_000 });
  await todayReady(page);
}

async function openAsk(page: Page): Promise<void> {
  await page.getByTestId("home-ask-open").click();
  await expect(page.getByTestId("ask-screen")).toBeVisible();
}

/** Ask one question, capturing "mid-thinking" (the orb and its one status line, no sentence
 *  yet) and "mid-stream" (the first sentence on screen, the trace of an answer still
 *  arriving), and wait for the finished answer. */
async function askAndCapture(page: Page, question: string, prefix: string, out: string): Promise<void> {
  await delayAskStream(page, 900);
  await page.getByLabel("Your question").fill(question);
  const clicked = page.getByTestId("ask-send").click();
  // Fired, not awaited: `send()` already set `busy` and rendered the orb and the status line
  // synchronously, before the network call it kicked off has any chance to resolve.
  await expect(page.getByTestId("ask-orb")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("ask-trace")).toBeVisible({ timeout: 5_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${out}/${prefix}-mid-thinking.png`, animations: "disabled" });

  // Best-effort: the instant exactly one sentence is on screen, before a second lands.
  await page
    .waitForFunction(() => document.querySelectorAll('[data-testid="answer-line"]').length === 1, { timeout: 4_000 })
    .catch(() => undefined);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${out}/${prefix}-mid-stream.png`, animations: "disabled" });

  await clicked;
  await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
  await page.unroute(/\/(ask|turns)\/stream$/);
}

test.describe("cp4 Ask: mid-thinking, mid-stream, the finished answer, a two-turn thread", () => {
  test.use({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });

  test("1280x900, clipped to the phone frame", async ({ page }) => {
    await tryItAsPa(page);
    await openAsk(page);

    await askAndCapture(page, "What was my blood pressure, and how long ago was that?", "wide-turn1", OUT);
    await page.evaluate(() => document.fonts.ready);
    await page.locator("#phone-frame").screenshot({ path: `${OUT}/wide-turn1-finished.png`, animations: "disabled" });

    await askAndCapture(page, "When is my next visit?", "wide-turn2", OUT);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByTestId("ask-earlier-turns")).toBeVisible();
    await page.locator("#phone-frame").screenshot({ path: `${OUT}/wide-two-turn-thread.png`, animations: "disabled" });
  });
});

test.describe("cp4 Ask at 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });

  test("390x844, full-bleed", async ({ page }) => {
    await tryItAsPa(page);
    await openAsk(page);

    await askAndCapture(page, "What was my blood pressure, and how long ago was that?", "phone-turn1", OUT);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${OUT}/phone-turn1-finished.png`, animations: "disabled" });

    await askAndCapture(page, "When is my next visit?", "phone-turn2", OUT);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByTestId("ask-earlier-turns")).toBeVisible();
    await page.screenshot({ path: `${OUT}/phone-two-turn-thread.png`, animations: "disabled" });
  });
});
