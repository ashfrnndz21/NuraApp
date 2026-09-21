import { mkdirSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API, fixClock, seedMedicine, signInThroughTheApp } from "../e2e/helpers";
import { addProvider, auth, book, daysFromNow, EVERY_PART, letIn, openOwn, openRecord, placeholderPng, signInAs, type Papers, type Person } from "../e2e/record-helpers";

/** Checkpoint 3, "What it means for you" (package 7, `docs/design/experience-blueprint.html`
 *  scene `insight`): screen captures of the real app against a real seeded account — the
 *  medicine, the visit and the paper are all written through the real API the same way the
 *  end-to-end suite writes them (`cp3Insight.spec.ts`), and the screen itself is reached
 *  through the real confirm flow ("Looks right"), never a synthetic Playwright fixture of the
 *  screen's own content. The stream's steps, its headline and its card's own questions are the
 *  real backend's, read back exactly as they arrive; only the refusal capture holds a network
 *  response (the exact shape `test_a_closing_account_is_refused_on_the_paper_insight_routes`
 *  already proves the backend sends for a closing account — see `holdAsRefusal` below), the
 *  same "test tooling only, nothing faked in the app" allowance `cp4AskShots.spec.ts` already
 *  uses to hold a real response for a wide capture window.
 *
 *  Not a gate — run with `-c playwright.visual.config.ts tests/visual/cp3InsightShots.spec.ts`,
 *  writing into the folder below. */

const OUT = process.env.NURA_INSIGHT_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp3-insight";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

async function postWaitingPaper(request: APIRequestContext, pa: Pick<Papers, "token" | "profileId">, label: string): Promise<void> {
  const posted = await request.post(`${API}/profiles/${pa.profileId}/photos`, {
    ...auth(pa.token),
    data: { data: placeholderPng(label).toString("base64"), content_type: "image/png", captured_at: "2026-09-14T08:00:00Z" },
  });
  expect(posted.status(), await posted.text()).toBe(201);
}

async function openWaitingPaperReview(page: Page, phone: string, displayAs: string, caregiver = false): Promise<void> {
  await signInThroughTheApp(page, phone, displayAs);
  await openRecord(page);
  await page.getByTestId("record-papers").click();
  await page.getByTestId("waiting-paper").click();
  await expect(page.getByTestId("review-card")).toBeVisible();
  void caregiver;
}

/** Holds the insight stream just long enough for "mid-thinking" to be a reliable, unforced
 *  window (the same real-timing-window technique `cp4AskShots.spec.ts`'s own `delayAskStream`
 *  uses): the request still reaches the real backend, and the response handed back is its own,
 *  byte for byte — only its arrival in the browser is delayed. */
async function delayInsightStream(page: Page, ms: number): Promise<void> {
  await page.route(/\/insight\/stream$/, async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, ms));
    await route.fulfill({ response });
  });
}

/** The exact refusal shape the backend sends a closing account on this route
 *  (`test_a_closing_account_is_refused_on_the_paper_insight_routes`, `backend/tests/
 *  test_paper_insight.py`: `streamed.status_code == 403`, `streamed.json() == {"refusal":
 *  "AccountClosing"}`) — replayed here rather than actually closing the account, since closing
 *  it for real would also refuse the Papers list itself before "Looks right" is ever reached
 *  (`record-papers.spec.ts`'s own closing-account walk), leaving no way to drive the real UI to
 *  this screen at all. The app code path is entirely real; only this one network response is
 *  substituted, with the real shape a closing account really gets. */
async function holdAsRefusal(page: Page): Promise<void> {
  await page.route(/\/insight\/stream$/, (route) => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ refusal: "AccountClosing" }) }));
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

for (const viewport of [
  { width: 1280, height: 900, prefix: "wide", clip: true },
  { width: 390, height: 844, prefix: "phone", clip: false },
] as const) {
  test.describe(`cp3 insight at ${viewport.width}x${viewport.height}`, () => {
    // Plain viewport resize only — never `isMobile`/`hasTouch` (that emulation was found, in
    // this very suite, to occasionally race the fixture-photo POST into an "unreadable" result;
    // `cp3Insight.spec.ts`'s own geometry test at the same 390x844 size uses a plain resize too
    // and has never shown the same flake).
    test.use({ viewport: { width: viewport.width, height: viewport.height }, deviceScaleFactor: viewport.clip ? 2 : 1 });

    const shot = async (page: Page, name: string, options: { liveAnimation?: boolean } = {}) => {
      await settle(page);
      const target = viewport.clip ? page.locator("#phone-frame") : page;
      // `animations: "disabled"` fast-forwards every CSS transition to its end state — exactly
      // what a settled capture wants, but it would make "mid-headline" indistinguishable from
      // "assembled" (SoftText's own per-word blur-to-sharp is a running CSS animation): that one
      // capture alone is taken live, at the real, unforced moment `waitForTimeout` above lands.
      await target.screenshot({ path: `${OUT}/${viewport.prefix}-${name}.png`, animations: options.liveAnimation ? "allow" : "disabled" });
    };

    test(`${viewport.prefix}: mid-thinking, mid-headline, assembled, kept`, async ({ page, request }) => {
      const pa = await openOwn(request);
      const drTan = await addProvider(request, pa, "Dr Tan");
      await book(request, pa, drTan, await daysFromNow(request, 7), "check-up");
      await postWaitingPaper(request, pa, "lab-report-vitals-2026-09-10");
      await openWaitingPaperReview(page, pa.phone, "Pa");
      // His statin, added now (through the API, never the page): read once "Looks right"
      // starts the real stream below, so the card's own second question is really offered —
      // added after the card is open so it is never a second, ambiguous "waiting-paper" beside
      // the one already on screen (`seedMedicine`'s own leftover, unconfirmed label photo).
      await seedMedicine(request, pa.token, pa.profileId, { generic: "atorvastatin", strength: "20 mg", dose_text: "1 tab OD", quantity: 30 });

      await delayInsightStream(page, 900);
      const clicked = page.getByTestId("looks-right").click();
      // The screen exists, its orb and status line already on it, the instant "Looks right"
      // is tapped — well before the held network call resolves.
      await expect(page.getByTestId("insight-thinking")).toBeVisible({ timeout: 5_000 });
      await shot(page, "mid-thinking");

      await clicked;
      await expect(page.getByTestId("insight-headline")).toBeVisible({ timeout: 15_000 });
      await page.unroute(/\/insight\/stream$/);
      // Mid-headline: the words are still arriving, blurred to sharp — real, unforced timing
      // inside SoftText's own 62ms-a-word pace, never a delay added by the app itself. The orb
      // beside it never leaves once the report has landed (the same "a finished turn keeps its
      // own orb" precedent Ask's own captures already show).
      await page.waitForTimeout(180);
      await shot(page, "mid-headline", { liveAnimation: true });

      // Assembled: the looked-at chips, the one card ("For Dr Tan on …"), its questions as
      // plain paragraphs, the safety line, the stacked actions.
      await expect(page.getByTestId("insight-card")).toBeVisible();
      await expect(page.getByTestId("insight-card").locator("h3")).toHaveText(/^For Dr Tan on /);
      await shot(page, "assembled");

      // Kept: the three-state button's own done check, and where the questions went, its own
      // row under the button.
      await page.getByTestId("insight-keep").click();
      await expect(page.getByTestId("insight-keep")).toHaveAttribute("data-state", "done");
      await expect(page.getByTestId("insight-kept-where")).toBeVisible();
      await shot(page, "kept");
    });

    test(`${viewport.prefix}: nothing to ask`, async ({ page, request }) => {
      const pa = await openOwn(request);
      await postWaitingPaper(request, pa, "lipid-panel-2023-09-07");
      await openWaitingPaperReview(page, pa.phone, "Pa");
      await page.getByTestId("looks-right").click();
      await expect(page.getByTestId("insight-headline")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("insight-card")).toHaveCount(0);
      await shot(page, "nothing-to-ask");
    });

    test(`${viewport.prefix}: no visit booked — the card's own generic title, never a guessed doctor`, async ({ page, request }) => {
      const pa = await openOwn(request);
      await postWaitingPaper(request, pa, "lab-report-vitals-2026-09-10");
      await openWaitingPaperReview(page, pa.phone, "Pa");
      await seedMedicine(request, pa.token, pa.profileId, { generic: "atorvastatin", strength: "20 mg", dose_text: "1 tab OD", quantity: 30 });
      await page.getByTestId("looks-right").click();
      await expect(page.getByTestId("insight-headline")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("insight-card").locator("h3")).toHaveText("For your next visit");
      await shot(page, "no-visit");
    });

    test(`${viewport.prefix}: a caregiver (Mei) — his paper, by name, never to him`, async ({ page, request }) => {
      const pa = await openOwn(request);
      const mei: Person = await letIn(request, pa, "Mei", "chief", EVERY_PART);
      const drTan = await addProvider(request, pa, "Dr Tan");
      await book(request, pa, drTan, await daysFromNow(request, 7), "check-up");
      await postWaitingPaper(request, pa, "lab-report-vitals-2026-09-10");
      await signInAs(page, mei, "Mei", true);
      await openRecord(page);
      await page.getByTestId("record-papers").click();
      await page.getByTestId("waiting-paper").click();
      await expect(page.getByTestId("review-card")).toBeVisible();
      await seedMedicine(request, pa.token, pa.profileId, { generic: "atorvastatin", strength: "20 mg", dose_text: "1 tab OD", quantity: 30 });
      await page.getByTestId("looks-right").click();
      await expect(page.getByTestId("insight-headline")).toBeVisible({ timeout: 15_000 });
      await expect(page.locator("h1")).toHaveText("What it means for Pa");
      await shot(page, "caregiver-mei");
    });

    test(`${viewport.prefix}: refusal`, async ({ page, request }) => {
      const pa = await openOwn(request);
      await postWaitingPaper(request, pa, "lab-report-vitals-2026-09-10");
      await openWaitingPaperReview(page, pa.phone, "Pa");
      await holdAsRefusal(page);
      await page.getByTestId("looks-right").click();
      await expect(page.getByTestId("notice")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("insight-leave")).toBeVisible();
      await shot(page, "refusal");
    });
  });
}
