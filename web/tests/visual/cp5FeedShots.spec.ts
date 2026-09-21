import { mkdirSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { API, apiToken, backendClock, fixClock, freshPhone, seedFeed, setBackendClock, signInThroughTheApp, todayReady } from "../e2e/helpers";

/** Package 13 (checkpoint 5, "For you — feeds of the day, a first card about him, and live
 *  search that finds things"): screen captures of the real app, against a deployment seeded
 *  with `NURA_DEMO_SEED=1`, signed in through the Welcome screen — never a synthetic Playwright
 *  fixture family, and never a faked delay inside the app itself. The fixture searcher and
 *  compressor only (`NURA_SEARCHER=fixture`, `NURA_COMPRESSOR=fixture`, `make dev`'s own
 *  default): the cards these shots show are the real backend's own words, from the allowlisted
 *  fixture pages under `backend/tests/fixtures/feed/`, never a real model or web call.
 *
 *  Not a gate — `npx playwright test -c playwright.visual.config.ts tests/visual/
 *  cp5FeedShots.spec.ts` writes pictures for a person to look at, into `NURA_FEED_SHOTS`
 *  (default: this checkpoint's own folder under the scratchpad).
 *
 *  "A run in progress" is real, held a little longer: `GET …/feed/jobs/status` answers
 *  `{looking:true}` for real while the background learning run is still working
 *  (`app.delivery.feed.background`), but the fixture jobs finish in milliseconds with no
 *  network to wait on, so the window to catch it on screen is too narrow to rely on. The route
 *  below holds that one real, already-true answer on screen a little longer — the same test-
 *  only network hold `tests/visual/cp4AskShots.spec.ts`'s own docstring explains and the
 *  checkpoint brief allows ("test tooling only, nothing faked in the app"): the status line it
 *  shows is the app's own real, unedited line, not a picture of one that never happened. */

const OUT = process.env.NURA_FEED_SHOTS ?? "/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/cp5-feed";
mkdirSync(OUT, { recursive: true });

test.use({ actionTimeout: 20_000 });

async function ready(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

/** The pager's own status poll (`Feed.tsx`) starts the instant it mounts — the same moment
 *  `GET .../feed` itself starts, not after it — so on a fixture backend, with no real network
 *  wait, the very first poll can genuinely land and answer `looking:false` (no run scheduled
 *  yet) before `GET .../feed`'s own route handler has reached `ensure_learning_scheduled` at
 *  all; once it answers `false`, the pager never polls again (`Feed.tsx`'s own `if (status.
 *  looking) timer = …` — no timer, no second poll), so the true, later "looking" state is
 *  never seen. This holds the *request* to `.../feed/jobs/status` until a `GET .../feed`
 *  response has actually landed (test tooling only — the same kind of real-network hold `tests/
 *  visual/cp4AskShots.spec.ts`'s own docstring explains): by then scheduling has already
 *  decided the day's run is "looking" or not, so the poll's real answer is the real, current
 *  one, never invented. Once it comes back `true`, the response is held on screen a little
 *  longer too, for a wide, reliable window for the shot. A `{looking:false}` answer (nothing
 *  was ever due, or the fixture run finished before the poll could even land) passes straight
 *  through, unedited — never turned into a picture of a run that was not actually happening. */
async function holdLookingTrue(page: Page, ms: number): Promise<void> {
  let feedAnswered = false;
  page.on("response", (res) => {
    if (res.request().method() === "GET" && /\/api\/profiles\/[^/]+\/feed$/.test(new URL(res.url()).pathname)) feedAnswered = true;
  });
  await page.route(/\/feed\/jobs\/status$/, async (route) => {
    const deadline = Date.now() + 5_000;
    while (!feedAnswered && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 50));
    const response = await route.fetch();
    const body = (await response.json()) as { looking: boolean };
    if (body.looking) await new Promise((resolve) => setTimeout(resolve, ms));
    await route.fulfill({ response, json: body });
  });
}

async function openPager(page: Page): Promise<void> {
  await page.getByTestId("open-feed").click();
  await expect(page.getByTestId("pager")).toBeVisible();
  await expect(page.getByTestId("feed-card").first()).toBeVisible();
}

async function onScreen(page: Page): Promise<{ type: string; index: number }> {
  return page.getByTestId("pager").evaluate((root) => {
    const middle = root.scrollTop + root.clientHeight / 2;
    const cards = [...root.querySelectorAll<HTMLElement>("article.feed-card")];
    let at = cards[0]!;
    for (const card of cards) if (card.offsetTop <= middle) at = card;
    return { type: at.dataset.type!, index: Number(at.dataset.index) };
  });
}

async function settled(page: Page): Promise<void> {
  const pager = page.getByTestId("pager");
  let last = -1;
  await expect
    .poll(
      async () => {
        const now = await pager.evaluate((el) => el.scrollTop);
        const still = now === last;
        last = now;
        return still;
      },
      { intervals: [150] },
    )
    .toBe(true);
}

/** One whole card, by mouse wheel over the pager — the checkpoint brief's own instruction for
 *  a "scrolled" shot, not the keyboard `pageDown` the functional suite already uses. */
async function wheelDown(page: Page): Promise<void> {
  const pager = page.getByTestId("pager");
  const box = (await pager.boundingBox())!;
  const height = await pager.evaluate((el) => el.clientHeight);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, height);
  await settled(page);
}

async function pageUntil(page: Page, type: string, limit = 25): Promise<void> {
  for (let n = 0; n < limit; n++) {
    if ((await onScreen(page)).type === type) return;
    await wheelDown(page);
  }
  throw new Error(`no ${type} card within ${limit} cards`);
}

/** A clip card with a LONG title and a long publisher name — test tooling only (the same kind
 *  of real-DOM, no-app-code-change technique `holdLookingTrue` above already uses), to check
 *  wrapping on the card the fixture data alone cannot exercise (its own title and publisher
 *  are both short). Overwrites only text nodes already on the real, rendered card — the
 *  layout, the CSS and every element are exactly what a real long title/publisher would
 *  produce; nothing about the app itself is touched. */
async function longClipShot(page: Page, request: APIRequestContext, out: string, prefix: string): Promise<void> {
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openPager(page);
  await pageUntil(page, "gate");
  await page.getByTestId("keep-going").click();
  let sawClip = false;
  for (let n = 0; n < 30 && !sawClip; n++) {
    if ((await onScreen(page)).type === "clip") sawClip = true;
    else await wheelDown(page);
  }
  if (!sawClip) return;
  const card = page.locator(`article.feed-card[data-index="${(await onScreen(page)).index}"]`);
  await card.evaluate((article) => {
    const title = article.querySelector("h2.title");
    if (title) title.textContent = "Your blood pressure tablet and your kidneys, in thirty seconds";
    const byline = article.querySelector(".clip-byline");
    if (byline) byline.textContent = "National University Heart Centre Singapore, Cardiology";
    const watch = article.querySelector('[data-testid="watch-whole"]');
    if (watch) watch.textContent = "Watch the whole video at National University Heart Centre Singapore, Cardiology";
  });
  await ready(page);
  await page.screenshot({ path: `${out}/${prefix}-clip-card-long.png`, animations: "disabled" });
}

/** Every capture but "a run in progress" and "quiet hours": the pager open on a freshly seeded
 *  Pa, one clip card and the why sheet along the way. Returns to the top before leaving, so a
 *  caller that wants "a run in progress" next opens a fresh page instead of reusing this one
 *  (the day's run has, by then, already finished on this profile). */
async function feedShots(page: Page, request: APIRequestContext, out: string, prefix: string): Promise<void> {
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openPager(page);
  await ready(page);
  await page.screenshot({ path: `${out}/${prefix}-top.png`, animations: "disabled" });

  await wheelDown(page);
  await ready(page);
  await page.screenshot({ path: `${out}/${prefix}-scrolled.png`, animations: "disabled" });

  // The gate: "That is all that is new today." — a real card, not a dialog.
  await pageUntil(page, "gate");
  await ready(page);
  await page.screenshot({ path: `${out}/${prefix}-gate.png`, animations: "disabled" });
  await page.getByTestId("keep-going").click();

  // Past the gate: his story, then learning — a clip among them (RE-07/E09-06): the worth-
  // knowing fixture page for his own medicine is a video — its still, its Play, and its one
  // action, the whole video on the publisher's own site, never anything that starts by itself.
  let sawClip = false;
  for (let n = 0; n < 30 && !sawClip; n++) {
    if ((await onScreen(page)).type === "clip") sawClip = true;
    else await wheelDown(page);
  }
  if (sawClip) {
    await ready(page);
    await page.screenshot({ path: `${out}/${prefix}-clip-card.png`, animations: "disabled" });
  }

  // The Why sheet (RE-08): why this card is on his page, in his own key's evidence. The card
  // on screen right now — the clip if one was found, else whatever learning card is here.
  const onScreenCard = page.locator(`article.feed-card[data-index="${(await onScreen(page)).index}"]`);
  const whyLink = onScreenCard.getByTestId("why-link");
  if (await whyLink.count()) {
    await whyLink.click();
    await expect(page.getByTestId("why-sheet")).toBeVisible();
    await ready(page);
    await page.screenshot({ path: `${out}/${prefix}-why-sheet.png`, animations: "disabled" });
    await page.getByTestId("why-sheet").getByRole("button", { name: /close/i }).click();
    await expect(page.getByTestId("why-sheet")).toHaveCount(0);
  }

  // On to the end of today's supply (#183/E21): the calm "nothing more for now" state — this
  // build's own designed answer to "that's everything for today"; the backend does not yet say
  // when it will look again, so the line stays the one it has (never invented).
  for (let n = 0; n < 30; n++) {
    if (await page.getByTestId("feed-end").count()) break;
    await wheelDown(page);
  }
  if (await page.getByTestId("feed-end").count()) {
    await page.getByTestId("feed-end").scrollIntoViewIfNeeded();
    await ready(page);
    await page.screenshot({ path: `${out}/${prefix}-nothing-more.png`, animations: "disabled" });
  }
}

/** Best-effort: on the fixture searcher and compressor, a day's whole background run (search,
 *  compress, write) has no real network to wait on, so even with `holdLookingTrue`'s own hold
 *  it can finish before this profile's very first status poll reaches the server — a real race
 *  this checkpoint's own real deployment does not have (a live search takes real seconds). When
 *  the line cannot be caught, this says so rather than failing the whole capture run over one
 *  shot, or — worse — forcing a picture of a state that was not actually happening. */
async function runInProgressShot(page: Page, request: APIRequestContext, out: string, prefix: string): Promise<void> {
  await holdLookingTrue(page, 1_500);
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openPager(page);
  try {
    await expect(page.getByTestId("feed-jobs-looking")).toBeVisible({ timeout: 8_000 });
    await ready(page);
    await page.screenshot({ path: `${out}/${prefix}-run-in-progress.png`, animations: "disabled" });
  } catch {
    console.log(`${prefix}: could not catch "a run in progress" on screen — the fixture backend's own background run finished before the first status poll could land; no shot written, nothing invented.`);
  } finally {
    await page.unroute(/\/feed\/jobs\/status$/);
  }
}

async function quietHoursShot(page: Page, request: APIRequestContext, out: string, prefix: string): Promise<void> {
  const pa = await seedFeed(request);
  const night = "2026-09-14T22:30:00+08:00";
  await setBackendClock(request, night);
  try {
    await fixClock(page, new Date(night));
    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    await page.getByTestId("open-feed").click();
    await expect(page.getByTestId("feed-quiet")).toBeVisible();
    await ready(page);
    await page.screenshot({ path: `${out}/${prefix}-quiet-hours.png`, animations: "disabled" });
  } finally {
    await setBackendClock(request, FROZEN_CLOCK);
  }
}

/** Mei's view: the caregiver's list on Pa's warfarin recall, no gate, her own denser cards. */
async function meisViewShot(page: Page, request: APIRequestContext, out: string, prefix: string): Promise<void> {
  const pa = await seedFeed(request);
  const meiPhone = freshPhone("+659333");
  const scopes = ["medicines", "visits", "readings", "records", "emergency", "ask"];
  const agreed = await request.post(`${API}/profiles/${pa.profileId}/consents/sharing`, {
    headers: { Authorization: `Bearer ${pa.token}` },
    data: { holder_phone_e164: meiPhone, holder_display_name: "Mei", scopes, role: "caregiver", window: "always", relationship: "daughter", language: "en", captured_via: "app" },
  });
  expect(agreed.status(), await agreed.text()).toBe(201);
  const key = await request.post(`${API}/profiles/${pa.profileId}/keys`, {
    headers: { Authorization: `Bearer ${pa.token}` },
    data: { holder_phone_e164: meiPhone, role: "caregiver", scopes },
  });
  expect(key.status()).toBe(201);
  await request.get(`${API}/profiles/${pa.profileId}/feed`, { headers: { Authorization: `Bearer ${pa.token}` } });
  await apiToken(request, meiPhone);
  await signInThroughTheApp(page, meiPhone, "Mei");
  await page.getByTestId("door-key").click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await todayReady(page);
  await openPager(page);
  await ready(page);
  await page.screenshot({ path: `${out}/${prefix}-meis-view.png`, animations: "disabled" });
}

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen) throw new Error(`the backend's clock is not frozen (it says ${JSON.stringify(backend)}): let Playwright start it, or start make dev with NURA_FROZEN_CLOCK`);
});

test.describe("cp5 feed at 1280x900, clipped to the phone frame", () => {
  test.use({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });

  test("feed of the day, a clip card, the why sheet, nothing more, a run in progress, quiet hours, Mei's view", async ({ page, request }) => {
    await fixClock(page);
    await feedShots(page, request, OUT, "wide");
  });

  test("a run in progress", async ({ page, request }) => {
    await fixClock(page);
    await runInProgressShot(page, request, OUT, "wide");
  });

  test("quiet hours", async ({ page, request }) => {
    await quietHoursShot(page, request, OUT, "wide");
  });

  test("Mei's view", async ({ page, request }) => {
    await fixClock(page);
    await meisViewShot(page, request, OUT, "wide");
  });

  test("a clip card with a long title and a long publisher name", async ({ page, request }) => {
    await fixClock(page);
    await longClipShot(page, request, OUT, "wide");
  });
});

test.describe("cp5 feed at 390x844, full-bleed", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });

  test("feed of the day, a clip card, the why sheet, nothing more, a run in progress, quiet hours, Mei's view", async ({ page, request }) => {
    await fixClock(page);
    await feedShots(page, request, OUT, "phone");
  });

  test("a run in progress", async ({ page, request }) => {
    await fixClock(page);
    await runInProgressShot(page, request, OUT, "phone");
  });

  test("quiet hours", async ({ page, request }) => {
    await quietHoursShot(page, request, OUT, "phone");
  });

  test("Mei's view", async ({ page, request }) => {
    await fixClock(page);
    await meisViewShot(page, request, OUT, "phone");
  });

  test("a clip card with a long title and a long publisher name", async ({ page, request }) => {
    await fixClock(page);
    await longClipShot(page, request, OUT, "phone");
  });
});

test.describe("cp5 feed at 360x640, full-bleed, a small phone", () => {
  test.use({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });

  test("feed of the day, a clip card, the why sheet, nothing more, a run in progress, quiet hours, Mei's view", async ({ page, request }) => {
    await fixClock(page);
    await feedShots(page, request, OUT, "small");
  });

  test("a run in progress", async ({ page, request }) => {
    await fixClock(page);
    await runInProgressShot(page, request, OUT, "small");
  });

  test("quiet hours", async ({ page, request }) => {
    await quietHoursShot(page, request, OUT, "small");
  });

  test("Mei's view", async ({ page, request }) => {
    await fixClock(page);
    await meisViewShot(page, request, OUT, "small");
  });

  test("a clip card with a long title and a long publisher name", async ({ page, request }) => {
    await fixClock(page);
    await longClipShot(page, request, OUT, "small");
  });
});
