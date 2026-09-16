import { expect, test, type Locator, type Page, type Response } from "@playwright/test";
import { BASE_URL, FROZEN_CLOCK } from "../../playwright.config";
import {
  API,
  apiToken,
  backendClock,
  captureSpeech,
  expireEveryKeptPage,
  fixClock,
  freshPhone,
  medicinesInIndexedDb,
  seedFeed,
  seedVisit,
  seedWarfarinLabel,
  setBackendClock,
  shotAs,
  signInThroughTheApp,
  todayReady,
  keptKeys,
} from "./helpers";

/** Checkpoint 12: the vertical feed on a phone-sized screen, against `make dev` serving the
 *  build. Both clocks stand at 10:00 in Singapore on Monday 14 September — the phone's by
 *  Playwright's clock (`fixClock`), the backend's by NURA_FROZEN_CLOCK — so the now card, the
 *  quiet hours and "today" are the same whenever this runs. The quiet-hours test moves both to
 *  22:30 and puts the backend's back. */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)}): let Playwright start it, or start make dev with NURA_FROZEN_CLOCK`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

interface Item {
  item_id: string;
  type: string;
  supply: string;
  status: string;
  headline: string;
  body: string[];
  voice: string[];
  why: { plain?: string };
  boundary: string | null;
  rendered_from_state: string;
  autoplay: boolean;
}
interface FeedPage {
  items: Item[];
  cursor: string | null;
  next_cursor: string | null;
  quiet: boolean;
  audience: string;
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
const isFeedPage = (response: Response) => response.request().method() === "GET" && /\/api\/profiles\/[^/]+\/feed$/.test(new URL(response.url()).pathname);

/** Every feed page the app asks for from here on, with the cursor it asked with. */
function recordPages(page: Page): { cursor: string | null; body: FeedPage }[] {
  const seen: { cursor: string | null; body: FeedPage }[] = [];
  page.on("response", async (response) => {
    if (!isFeedPage(response) || !response.ok()) return;
    try {
      seen.push({ cursor: new URL(response.url()).searchParams.get("cursor"), body: (await response.json()) as FeedPage });
    } catch {
      // The test ended, or the page went, while this body was still coming: nothing to record.
    }
  });
  return seen;
}

/** How long a card must rest before it counts as opened (`OPENED_AFTER_MS`,
 *  `src/screens/Feed.tsx`, #189). Not imported: that module pulls in `ui/feed.css`, which the
 *  test runner's plain Node loader cannot parse. */
const OPENED_AFTER_MS = 400;

/** Every "opened", "played", … event the app sent from here on (E11-08, `POST …/feed/events`). */
function recordEvents(page: Page): { item_id: string; event: string }[] {
  const seen: { item_id: string; event: string }[] = [];
  page.on("request", (req) => {
    if (req.method() !== "POST" || !/\/feed\/events$/.test(new URL(req.url()).pathname)) return;
    const body = req.postDataJSON() as { events: { item_id: string; event: string }[] };
    seen.push(...body.events.map((one) => ({ item_id: one.item_id, event: one.event })));
  });
  return seen;
}

async function openPager(page: Page): Promise<void> {
  await page.getByTestId("open-feed").click();
  await expect(page.getByTestId("pager")).toBeVisible();
  await expect(page.getByTestId("feed-card").first()).toBeVisible();
}

/** Wait until the pager has stopped moving. */
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

/** Page Down on the pager, from the card on screen, and wait for it to settle on the next. */
async function pageDown(page: Page): Promise<void> {
  const pager = page.getByTestId("pager");
  const inside = await pager.evaluate((el) => el.contains(document.activeElement));
  if (!inside) {
    const { index } = await onScreen(page);
    await page.locator(`article.feed-card[data-index="${index}"]`).focus();
  }
  const before = await pager.evaluate((el) => el.scrollTop);
  await page.keyboard.press("PageDown");
  await expect.poll(() => pager.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
  await settled(page);
}

/** The card across the pager's middle: the one on screen. */
async function onScreen(page: Page): Promise<{ type: string; supply: string; itemId: string; index: number }> {
  return page.getByTestId("pager").evaluate((root) => {
    const middle = root.scrollTop + root.clientHeight / 2;
    const cards = [...root.querySelectorAll<HTMLElement>("article.feed-card")];
    let at = cards[0]!;
    for (const card of cards) if (card.offsetTop <= middle) at = card;
    return { type: at.dataset.type!, supply: at.dataset.supply!, itemId: at.dataset.itemId!, index: Number(at.dataset.index) };
  });
}

async function pageUntil(page: Page, type: string, limit = 20): Promise<void> {
  for (let n = 0; n < limit; n++) {
    if ((await onScreen(page)).type === type) return;
    await pageDown(page);
  }
  throw new Error(`no ${type} card within ${limit} cards`);
}

async function spoken(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
}

test("the pager: one card a screen, in the backend's order, the gate, endless past it on stable cursors, nothing plays by itself", async ({ page, request }) => {
  await captureSpeech(page);
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);

  const pages = recordPages(page);
  await openPager(page);
  await expect.poll(() => pages.length).toBeGreaterThan(0);
  const first = pages[0]!;
  expect(first.cursor).toBeNull();
  const firstItems = first.body.items;
  expect(firstItems.map((item) => item.type).slice(0, 3)).toEqual(["now", "reorder", "reading"]);

  // The backend's order, its words and its State on every card; nothing re-ranked, nothing set to play.
  const cards = page.getByTestId("feed-card");
  await expect.poll(async () => (await cards.evaluateAll((els) => els.map((el) => (el as HTMLElement).dataset.itemId))).slice(0, firstItems.length)).toEqual(firstItems.map((item) => item.item_id));
  for (const [at, item] of firstItems.entries()) {
    const card = cards.nth(at);
    await expect(card.locator("h2")).toHaveText(item.headline);
    await expect(card).toHaveAttribute("data-state-id", item.rendered_from_state);
    for (const line of item.body) await expect(card).toContainText(line);
    if (item.why.plain) await expect(card.getByTestId("why")).toHaveText(item.why.plain);
    expect(item.autoplay).toBe(false);
  }

  // One card per screen: the pager snaps on y, and a card is the pager's height.
  const pager = page.getByTestId("pager");
  expect(await pager.evaluate((el) => getComputedStyle(el).scrollSnapType)).toBe("y mandatory");
  expect(await pager.evaluate((el) => getComputedStyle(el).overscrollBehaviorY)).toBe("contain");
  const height = await pager.evaluate((el) => el.clientHeight);
  for (let at = 0; at < 3; at++) expect((await cards.nth(at).boundingBox())!.height).toBeGreaterThanOrEqual(height - 1);
  expect(await pager.getAttribute("role")).toBe("feed");
  await expect(cards.first()).toHaveAttribute("aria-posinset", "1");
  // Scroll smoothly by default; Reduce Motion is checked in its own test.
  expect(await pager.evaluate((el) => getComputedStyle(el).scrollBehavior)).toBe("smooth");

  // The keyboard: Page Down moves one whole card and focuses it.
  await cards.first().focus();
  await pageDown(page);
  expect((await onScreen(page)).index).toBe(1);
  await expect(cards.nth(1)).toBeFocused();

  // The gate is a real card; Keep going moves on to his story.
  await pageUntil(page, "gate");
  const gate = page.locator("article.feed-card[data-type=gate]").first();
  await expect(gate).toContainText("That is all that is new today.");
  await expect(gate.getByTestId("action-notForMe")).toHaveCount(0);
  await gate.getByTestId("keep-going").click();
  // Past the gate: his story and learning — his week in 30 seconds and a clip are among them.
  await expect.poll(async () => (await onScreen(page)).supply).toMatch(/^(story|learning)$/);

  // Past the gate it pages on: each next page asked for once, by the cursor the page before
  // handed back, and everything past the gate is his story or learning.
  for (let n = 0; n < 12; n++) await pageDown(page);
  await expect.poll(() => pages.length).toBeGreaterThanOrEqual(3);
  const cursors = pages.map((each) => each.cursor);
  expect(cursors[0]).toBeNull();
  expect(new Set(cursors).size).toBe(cursors.length);
  for (let at = 1; at < pages.length; at++) expect(pages[at]!.cursor).toBe(pages[at - 1]!.body.next_cursor);
  const shown = await cards.evaluateAll((els) => els.map((el) => (el as HTMLElement).dataset.supply!));
  const gateAt = shown.indexOf("gate");
  expect(shown.length).toBeGreaterThan(firstItems.length * 2);
  expect(new Set(shown.slice(gateAt + 1))).toEqual(new Set(["story", "learning"]));

  // The pager mid-scroll, for the checkpoint note: snapping held off for one frame's picture.
  await pager.evaluate((el) => {
    el.style.scrollSnapType = "none";
    el.style.scrollBehavior = "auto";
    el.scrollTop = el.clientHeight * 1.45;
  });
  await shotAs(page, "w2-feed-pager-mid-scroll");
  await pager.evaluate((el) => {
    el.style.scrollSnapType = "";
    el.style.scrollBehavior = "";
  });

  // Nothing played by itself, through all of that; nothing scrolls sideways.
  expect(await spoken(page)).toEqual([]);
  expect(await page.evaluate(() => [...document.querySelectorAll("audio")].filter((el) => !el.paused).length)).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth));
  expect(await pager.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
});

test("a card scrolled past fast is never opened; one rested on is opened exactly once (#189)", async ({ page, request }) => {
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  const events = recordEvents(page);
  await openPager(page);
  await settled(page);
  // The first card's own settle, from opening the pager, is not what this test is about.
  await page.waitForTimeout(OPENED_AFTER_MS + 100);
  events.length = 0;

  const pager = page.getByTestId("pager");
  const cards = await pager.evaluate((root) => [...root.querySelectorAll<HTMLElement>("article.feed-card")].map((el) => ({ itemId: el.dataset.itemId!, top: el.offsetTop })));
  const [, passedOver, restedOn] = cards;

  // Fast: straight past the second card to the third, with no dwell on the one passed —
  // every settle in between restarts the wait, so it is cleared before it can fire.
  await pager.evaluate((el, top) => (el.scrollTop = top), passedOver!.top);
  await pager.evaluate((el, top) => (el.scrollTop = top), restedOn!.top);
  await expect.poll(() => onScreen(page).then((s) => s.itemId)).toBe(restedOn!.itemId);

  // Now it rests: opened once, for the card it rests on — polled generously rather than
  // timed, so this holds under load, not just on a quiet machine.
  await expect
    .poll(() => events.filter((one) => one.item_id === restedOn!.itemId && one.event === "opened").length, { timeout: 15_000 })
    .toBe(1);
  // Never for the card scrolled past on the way here.
  expect(events.filter((one) => one.item_id === passedOver!.itemId && one.event === "opened")).toEqual([]);
});

test("a learning card: its lines, its boundary, its why, four side actions; Hear on tap only, stopped when it leaves; Not for me holds the kind", async ({ page, request }) => {
  await captureSpeech(page);
  // The backend's own voice of a card (E11, GET …/feed/{item}/voice) plays through an audio
  // element: count what is played, and play nothing aloud here.
  await page.addInitScript(() => {
    const played: string[] = [];
    (window as unknown as { __played: string[] }).__played = played;
    class Heard extends window.Audio {
      override play(): Promise<void> {
        played.push(this.src);
        return Promise.resolve();
      }
      override pause(): void {}
    }
    Object.defineProperty(window, "Audio", { value: Heard, configurable: true });
  });
  const played = () => page.evaluate(() => (window as unknown as { __played: string[] }).__played);
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  const pages = recordPages(page);
  const voiceAsks: [string, number][] = [];
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (/\/feed\/[^/]+\/voice$/.test(path)) voiceAsks.push([path, response.status()]);
  });
  await openPager(page);
  await pageUntil(page, "learning");

  const { itemId } = await onScreen(page);
  const item = pages.flatMap((each) => each.body.items).find((each) => each.item_id === itemId)!;
  const card = page.locator(`article.feed-card[data-item-id="${itemId}"]`).first();
  const boundary = item.boundary!.split("\n");
  // Every line the backend wrote, the boundary kept apart and last, the why under it.
  for (const line of item.body.slice(0, item.body.length - boundary.length)) await expect(card.getByTestId("lines")).toContainText(line);
  await expect(card.getByTestId("lines")).toContainText("This comes from HealthHub.");
  await expect(card.getByTestId("boundary")).toHaveText(boundary.join(""));
  await expect(card.getByTestId("boundary").locator("p").last()).toHaveText("Ask your doctor.");
  await expect(card.getByTestId("why")).toHaveText(item.why.plain!);
  await expect(card.locator(".feed-section")).toHaveText("In simple words");
  // Four side actions, each a visible word, each at least 56 by 56.
  for (const [action, word] of [["hear", "Hear"], ["ask", "Ask"], ["family", "Family"], ["notForMe", "Not for me"]] as const) {
    const button = card.getByTestId(`action-${action}`);
    await expect(button).toBeVisible();
    await expect(button).toHaveText(word);
    const box = (await button.boundingBox())!;
    expect(box.height).toBeGreaterThanOrEqual(56);
    expect(box.width).toBeGreaterThanOrEqual(56);
  }
  await shotAs(page, "w2-feed-learning-card-side-actions");

  // No voice before the tap. The warm-up fetched this card's own voice from the backend (E11):
  // bytes only, 200, and nothing played or said.
  await expect.poll(() => voiceAsks.filter(([path, status]) => path.endsWith(`/feed/${itemId}/voice`) && status === 200).length).toBeGreaterThan(0);
  await settled(page);
  expect(await spoken(page)).toEqual([]);
  expect(await played()).toEqual([]);
  const engaged = page.waitForRequest((req) => req.method() === "POST" && req.url().includes(`/feed/${itemId}/engagement`));
  await card.getByTestId("action-hear").click();
  // Hear plays the backend's voice of this card, once; the phone's voice says nothing.
  await expect.poll(() => played().then((each) => each.length)).toBe(1);
  expect(await spoken(page)).toEqual([]);
  expect((await engaged).postDataJSON()).toEqual({ event: "heard", channel: "app" });

  // It stops when the card leaves the screen, and the next card does not start.
  const cancels = await page.evaluate(() => (window as unknown as { __cancels: number }).__cancels);
  await card.focus();
  await pageDown(page);
  await expect.poll(() => page.evaluate(() => (window as unknown as { __cancels: number }).__cancels)).toBeGreaterThan(cancels);
  expect(await played()).toHaveLength(1);
  expect(await spoken(page)).toEqual([]);

  // Back to the learning card: Not for me posts `dismissed`, the card says so.
  await page.keyboard.press("PageUp");
  await expect.poll(async () => (await onScreen(page)).itemId).toBe(itemId);
  await settled(page);
  const dismissed = page.waitForRequest((req) => req.method() === "POST" && req.url().includes(`/feed/${itemId}/engagement`) && req.postDataJSON()?.event === "dismissed");
  await card.getByTestId("action-notForMe").click();
  await dismissed;
  await expect(card.getByTestId("note")).toContainText("Nura wrote down that this is not for you.");
  await expect(card.getByTestId("note")).toContainText("You will not see this kind of card again today.");
  await expect(card.getByTestId("action-notForMe")).toHaveCount(0);
  // #83's acceptance: the kind is held for the profile — no learning card on today's pages now.
  let cursor: string | null = null;
  const types: string[] = [];
  for (let n = 0; n < 3; n++) {
    const query: Record<string, string> = cursor ? { cursor } : {};
    const next = (await (await request.get(`${API}/profiles/${pa.profileId}/feed`, { ...auth(pa.token), params: query })).json()) as FeedPage;
    types.push(...next.items.map((each) => each.type));
    cursor = next.next_cursor;
    if (!cursor) break;
  }
  expect(types).not.toContain("learning");
});

test("Family sends a reading to the family thread by reference; a card it cannot carry says so; Ask answers from his papers and comes back to the same card", async ({ page, request }) => {
  await captureSpeech(page);
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openPager(page);

  await pageUntil(page, "reading");
  const reading = page.locator("article.feed-card[data-type=reading]").first();
  const posted = page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith(`/profiles/${pa.profileId}/thread`));
  await reading.getByTestId("action-family").click();
  expect((await posted).postDataJSON()).toEqual({ card_kind: "reading" });
  await expect(reading.getByTestId("note")).toHaveText("Your family can see this card now.");
  const thread = (await (await request.get(`${API}/profiles/${pa.profileId}/thread`, auth(pa.token))).json()) as { entries: { card_kind: string | null; text: string | null }[] };
  expect(thread.entries.map((entry) => [entry.card_kind, entry.text])).toContainEqual(["reading", null]);

  await pageUntil(page, "story");
  const story = (await onScreen(page)).index;
  const card = page.locator(`article.feed-card[data-index="${story}"]`);
  let sent = 0;
  page.on("request", (req) => {
    if (req.method() === "POST" && req.url().endsWith("/thread")) sent += 1;
  });
  await card.getByTestId("action-family").click();
  await expect(card.getByTestId("note")).toHaveText("Nura cannot send this card to your family yet.");
  expect(sent).toBe(0);

  // Ask: his question goes to E03's recall as he typed it, in voice mode (the patient's
  // density); the answer is the backend's cited lines, each under its source line, the
  // boundary last; Hear reads it on tap only.
  const headline = await card.locator("h2").textContent();
  await card.getByTestId("action-ask").click();
  const asking = page.getByTestId("ask-screen");
  await expect(asking).toContainText(headline!);
  await expect(asking).toHaveAttribute("data-mode", "voice");
  await asking.getByLabel("Your question").fill("What was my blood pressure?");
  const [asked, answered] = await Promise.all([
    page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith(`/profiles/${pa.profileId}/ask`)),
    page.waitForResponse((res) => res.request().method() === "POST" && res.url().endsWith(`/profiles/${pa.profileId}/ask`)),
    asking.getByTestId("ask-send").click(),
  ]);
  expect(asked.postDataJSON()).toEqual({ question: "What was my blood pressure?", mode: "voice", language: "en" });
  const reply = (await answered.json()) as { lines: { text: string }[]; honest: string[]; boundary: string[]; spoken: string[] };
  const shown = asking.getByTestId("answer");
  expect(reply.lines.length).toBeGreaterThan(0);
  await expect(shown.getByTestId("answer-line").locator("p:not(.provenance)")).toHaveText(reply.lines.map((line) => line.text));
  await expect(shown.getByTestId("answer-source").first()).toHaveText("This comes from your papers.");
  await expect(shown.getByTestId("boundary")).toHaveText(reply.boundary.join(""));
  // The boundary is last: below every answer line.
  const lastLine = (await shown.getByTestId("answer-lines").boundingBox())!;
  const boundaryBox = (await shown.getByTestId("boundary").boundingBox())!;
  expect(boundaryBox.y).toBeGreaterThanOrEqual(lastLine.y + lastLine.height - 1);
  expect(await spoken(page)).toEqual([]);
  await shown.getByTestId("hear").click();
  expect(await spoken(page)).toEqual(reply.spoken);
  await page.getByTestId("back-to-cards").click();
  await expect(page.getByTestId("pager")).toBeVisible();
  await expect.poll(async () => (await onScreen(page)).index).toBe(story);
});

test("the caregiver's list: no gate, what was held from him shown as held, and a refusal said in one plain sentence", async ({ page, request }) => {
  const pa = await seedFeed(request);
  await seedWarfarinLabel(request, pa.token, pa.profileId);
  const mei = freshPhone("+659333");
  const scopes = ["medicines", "visits", "readings", "records", "emergency", "ask"];
  const agreed = await request.post(`${API}/profiles/${pa.profileId}/consents/sharing`, {
    ...auth(pa.token),
    data: { holder_phone_e164: mei, holder_display_name: "Mei", scopes, relationship: "daughter", language: "en", captured_via: "app" },
  });
  expect(agreed.status(), await agreed.text()).toBe(201);
  const key = await request.post(`${API}/profiles/${pa.profileId}/keys`, { ...auth(pa.token), data: { holder_phone_e164: mei, role: "caregiver", scopes } });
  expect(key.status()).toBe(201);
  // Pa's feed is rendered first, as his own morning would; Mei then reads what became of it.
  await request.get(`${API}/profiles/${pa.profileId}/feed`, auth(pa.token));
  await apiToken(request, mei);

  await signInThroughTheApp(page, mei, "Mei");
  await page.getByTestId("door-key").click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await todayReady(page);
  const pages = recordPages(page);
  await openPager(page);
  await expect.poll(() => pages.length).toBeGreaterThan(0);
  expect(pages[0]!.body.audience).toBe("caregiver");
  const types = await page.getByTestId("feed-card").evaluateAll((els) => els.map((el) => (el as HTMLElement).dataset.type));
  expect(types).not.toContain("gate");

  const notice = page.locator("article.feed-card[data-type=notice]").first();
  await notice.scrollIntoViewIfNeeded();
  await expect(notice.getByTestId("status")).toHaveText("Nura kept this back from Pa.");
  await expect(notice.getByTestId("boundary")).toContainText("This is not a doctor's advice.");
  await expect(page.locator("article.feed-card[data-type=reading]").first().getByTestId("status")).toHaveText(/This was on the page Pa sees\.|Pa opened this card\./);
  await expect(page.locator("article.feed-card[data-type=duty] [data-testid=status]")).toHaveCount(0);

  // Her key does not open the family thread: the refusal is said, and the card stays.
  const reading = page.locator("article.feed-card[data-type=reading]").first();
  await reading.scrollIntoViewIfNeeded();
  await reading.getByTestId("action-family").click();
  await expect(page.getByTestId("notice")).toHaveText("This part of the papers is not open to you.");
  await expect(page.getByTestId("notice")).not.toContainText("OutOfScope");
  await expect(reading).toBeVisible();

  // She asks in text mode (the caregiver's density), and reads the backend's lines.
  await reading.getByTestId("action-ask").click();
  const asking = page.getByTestId("ask-screen");
  await expect(asking).toHaveAttribute("data-mode", "text");
  await asking.getByLabel("Your question").fill("What was his blood pressure?");
  const [asked] = await Promise.all([
    page.waitForRequest((req) => req.method() === "POST" && req.url().endsWith(`/profiles/${pa.profileId}/ask`)),
    asking.getByTestId("ask-send").click(),
  ]);
  expect(asked.postDataJSON()).toMatchObject({ question: "What was his blood pressure?", mode: "text" });
  await expect(asking.getByTestId("answer").getByTestId("boundary")).toBeVisible();
});

test("quiet hours (both clocks at 22:30): the pager says Nura keeps quiet, with no card and no spinner", async ({ page, request }) => {
  const pa = await seedFeed(request);
  const night = "2026-09-14T22:30:00+08:00";
  await setBackendClock(request, night);
  try {
    await fixClock(page, new Date(night));
    await signInThroughTheApp(page, pa.phone, "Pa");
    await todayReady(page);
    await page.getByTestId("open-feed").click();
    await expect(page.getByTestId("feed-quiet")).toContainText("Nura keeps quiet at night.");
    await expect(page.getByTestId("feed-quiet")).toContainText("Your cards come back in the morning.");
    await expect(page.getByTestId("feed-card")).toHaveCount(0);
    expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  } finally {
    await setBackendClock(request, FROZEN_CLOCK);
  }
});

test("Reduce Motion: the pager moves a card at once, with no smooth scroll", async ({ page, request }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await openPager(page);
  const pager = page.getByTestId("pager");
  expect(await pager.evaluate((el) => getComputedStyle(el).scrollBehavior)).toBe("auto");
  await page.getByTestId("feed-card").first().focus();
  await page.keyboard.press("PageDown");
  // No animation: the next card is at the top on the very next frame.
  const next = await page.getByTestId("feed-card").nth(1).evaluate((el) => (el as HTMLElement).offsetTop);
  await expect.poll(() => pager.evaluate((el) => el.scrollTop), { timeout: 500 }).toBe(next);
});

test("offline: the pager opens on the kept first page, dated, with no spinner; past midnight only the emergency card", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  const pages = recordPages(page);
  await openPager(page);
  await expect.poll(() => pages.length).toBeGreaterThan(0);
  const kept = pages[0]!.body.items.map((item) => item.item_id);
  await expect.poll(async () => (await keptKeys(page)).some((key) => key.startsWith("emergency."))).toBe(true);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((done) => navigator.serviceWorker.addEventListener("controllerchange", () => done(), { once: true }));
    }
  });

  await context.setOffline(true);
  await page.reload();
  await openPager(page);
  await expect(page.getByTestId("offline")).toContainText("These are your cards from earlier today.");
  await expect(page.getByTestId("offline")).toContainText(/Nura last read your papers on [A-Z][a-z]+day \d{1,2} [A-Z][a-z]+ at 10:00\s?am\./);
  expect(await page.getByTestId("feed-card").evaluateAll((els) => els.map((el) => (el as HTMLElement).dataset.itemId))).toEqual(kept);
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await shotAs(page, "w2-feed-offline-kept");

  // The next morning, still offline: every kept page is past its midnight and is deleted.
  expect(await expireEveryKeptPage(page)).toBe(2);
  await page.reload();
  // Today, past midnight: the emergency card rule, and no way into a page the phone no longer holds.
  await expect(page.getByTestId("cannot-reach")).toContainText("Nura cannot reach your papers right now.");
  await expect(page.getByTestId("emergency-card")).toContainText("Emergency card");
  await expect(page.getByTestId("open-feed")).toHaveCount(0);
  expect(await medicinesInIndexedDb(page)).toEqual([]);
  await context.setOffline(false);
});

/** Nothing is ever drawn over a line. At the centre of every line of the card — scrolled to
 *  inside the card's own region when it is below the fold — the element the page hits is that
 *  line: never a button, the tab bar or another card. After the region is scrolled to its end
 *  the last boundary line is hit too. Every button is hit at its own centre, clear of the tab
 *  bar, and (patient density) at least 56 by 56. */
async function everyLineReadable(card: Locator): Promise<string[]> {
  return card.evaluate(async (article) => {
    const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null))));
    const body = article.querySelector<HTMLElement>(".feed-body")!;
    const problems: string[] = [];
    const hit = (element: Element) => {
      const box = element.getBoundingClientRect();
      const at = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return at !== null && (at === element || element.contains(at));
    };
    const lines = [...body.querySelectorAll<HTMLElement>("h2, p")];
    if (lines.length === 0) problems.push("no lines");
    body.scrollTop = 0;
    await frame();
    for (const line of lines) {
      const region = body.getBoundingClientRect();
      const box = line.getBoundingClientRect();
      if (box.bottom > region.bottom) body.scrollTop += box.bottom - region.bottom + 2;
      else if (box.top < region.top) body.scrollTop -= region.top - box.top + 2;
      await frame();
      if (!hit(line)) problems.push(`covered: ${line.textContent}`);
    }
    body.scrollTop = body.scrollHeight;
    await frame();
    const lastBoundary = body.querySelector<HTMLElement>(".boundary p:last-child");
    if (lastBoundary && !hit(lastBoundary)) problems.push(`the last boundary line is covered at the end: ${lastBoundary.textContent}`);
    if (!hit(lines.at(-1)!)) problems.push(`the last line is covered at the end: ${lines.at(-1)!.textContent}`);
    const bar = document.querySelector("nav.tabbar")!.getBoundingClientRect();
    for (const button of article.querySelectorAll<HTMLElement>(".feed-controls button")) {
      const box = button.getBoundingClientRect();
      if (box.bottom > bar.top) problems.push(`under the tab bar: ${button.textContent}`);
      if (box.height < 56 || box.width < 56) problems.push(`smaller than 56: ${button.textContent}`);
      if (!hit(button)) problems.push(`button covered: ${button.textContent}`);
    }
    return problems;
  });
}

for (const [label, viewport] of [
  ["Pixel 5", null],
  ["a small phone, 360 by 640", { width: 360, height: 640 }],
] as const) {
  test.describe(`nothing covers a line — ${label}`, () => {
    if (viewport) test.use({ viewport });

    test(`a visit, a reorder and a learning card: every line readable, the boundary last and readable, the buttons clear of the tab bar (${label})`, async ({ page, request }) => {
      const pa = await seedFeed(request);
      await seedVisit(request, pa.token, pa.profileId);
      await signInThroughTheApp(page, pa.phone, "Pa");
      await todayReady(page);
      await openPager(page);
      for (const type of ["visit", "reorder", "learning"]) {
        await pageUntil(page, type);
        const { index } = await onScreen(page);
        const card = page.locator(`article.feed-card[data-index="${index}"]`);
        expect(await everyLineReadable(card), `${type} card, ${label}`).toEqual([]);
        if (type === "learning") {
          await expect(card.getByTestId("boundary").locator("p").last()).toHaveText("Ask your doctor.");
          if (viewport) await shotAs(page, "w2-feed-learning-card-small-phone-end");
        }
      }
    });
  });
}
