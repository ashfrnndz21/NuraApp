import { expect, test, type Page } from "@playwright/test";
import { BASE_URL, FROZEN_CLOCK } from "../../playwright.config";
import { auth, seedFamily, type Family, type Person } from "./familySeed";
import { API, backendClock, captureSpeech, fixClock, seedFeed, shotAs, signInThroughTheApp, openMe, todayReady} from "./helpers";

/** Checkpoint 28: the feed's richer formats (F1) on a phone-sized screen, against `make dev`
 *  serving the build, both clocks at 10:00 in Singapore on Monday 14 September. A clip card's
 *  still and captions come from Nura's own server and nothing plays until it is tapped; his week
 *  in 30 seconds; the chief's Watching and Sent panels on Home; the ask bar's filters; his town
 *  on Me, on his yes. The card made while he reads is `day.spec.ts`'s memo card. */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)}): let Playwright start it, or start make dev with NURA_FROZEN_CLOCK`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

/** Pre-rendered voices are recorded instead of played: Playwright's Chromium plays nothing. */
async function recordPlays(page: Page): Promise<() => Promise<number>> {
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
  return async () =>
    page.evaluate(() => (window as unknown as { __played: string[] }).__played.length + (window as unknown as { __spoken: string[] }).__spoken.length);
}

async function onScreen(page: Page): Promise<string> {
  return page.getByTestId("pager").evaluate((pager) => {
    const box = pager.getBoundingClientRect();
    const middle = box.top + box.height / 2;
    const card = [...pager.querySelectorAll<HTMLElement>("article.feed-card")].find((each) => {
      const at = each.getBoundingClientRect();
      return at.top <= middle && at.bottom >= middle;
    });
    return card?.dataset.type ?? "";
  });
}

async function pageUntil(page: Page, type: string): Promise<void> {
  const pager = page.getByTestId("pager");
  for (let n = 0; n < 24; n++) {
    if ((await onScreen(page)) === type) return;
    const before = await pager.evaluate((el) => el.scrollTop);
    await page.locator("article.feed-card").first().focus();
    await pager.evaluate((el) => el.scrollBy({ top: el.clientHeight }));
    await expect.poll(() => pager.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
  }
  throw new Error(`no ${type} card within 24 cards`);
}

async function openFeed(page: Page): Promise<void> {
  await todayReady(page);
  await page.getByTestId("open-feed").click();
  await expect(page.getByTestId("pager")).toBeVisible();
  await expect(page.locator("article.feed-card").first()).toBeVisible();
}

async function signIn(page: Page, who: Person, owner: boolean): Promise<void> {
  await signInThroughTheApp(page, who.phone, who.name);
  if (!owner) await page.getByTestId("door-key").click();
  await expect(page.getByTestId("tab-connect")).toBeVisible();
}

/** Pa's readings this week and today, and his feed composed once, as his phone would. */
async function readingsFor(request: Parameters<typeof seedFeed>[0], family: Family): Promise<void> {
  const his = { headers: auth(family.pa.token) };
  for (const [daysAgo, systolic, diastolic] of [
    [7, 146, 90],
    [3, 142, 88],
    [0, 138, 84],
  ] as const) {
    const taken_at = new Date(Date.parse(FROZEN_CLOCK) - daysAgo * 86_400_000).toISOString();
    const added = await request.post(`${API}/profiles/${family.profileId}/readings`, { ...his, data: { systolic, diastolic, taken_at } });
    expect(added.status()).toBe(201);
  }
  expect((await request.get(`${API}/profiles/${family.profileId}/feed`, his)).status()).toBe(200);
}

const NURA = new Set([new URL(API).host, new URL(BASE_URL).host]);
/** The publisher's own site and the video platforms: none is asked for anything by the app. */
const VIDEO_SITES = /(^|\.)(nhcs\.com\.sg|singhealth\.com\.sg|youtube\.com|youtu\.be|ytimg\.com|googlevideo\.com|vimeo\.com|facebook\.com|tiktok\.com)$/;

test("a clip: its still from Nura's own server, Play on a tap only, the line being said under it, the whole video on the publisher's site", async ({ page, request }) => {
  await captureSpeech(page);
  const plays = await recordPlays(page);
  const hosts = new Set<string>();
  const asked: string[] = [];
  page.on("request", (request) => {
    asked.push(request.url());
    hosts.add(new URL(request.url()).host);
  });
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await openFeed(page);
  await pageUntil(page, "clip");
  const card = page.locator("article.feed-card[data-type=clip]").first();
  await expect(card.locator("h2.title")).toHaveText("Your blood pressure, in 30 seconds");
  const still = card.getByTestId("clip-poster");
  await expect(still).toBeVisible();
  expect(await still.getAttribute("src")).toMatch(/^blob:/);
  // Nothing plays when the card arrives, and no caption shows.
  await page.waitForTimeout(500);
  expect(await plays()).toBe(0);
  await expect(card.getByTestId("clip-caption")).toHaveCount(0);
  // The whole video is on the heart centre's own site: a link he taps, in a tab of its own.
  const link = card.getByTestId("watch-whole");
  await expect(link).toHaveText("Watch the whole video at National Heart Centre Singapore");
  await expect(link).toHaveAttribute("href", "https://www.nhcs.com.sg/patient-care/videos/understanding-high-blood-pressure");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  // Every card keeps Hear and Not for me.
  await expect(card.getByTestId("action-hear")).toBeVisible();
  await expect(card.getByTestId("action-notForMe")).toBeVisible();
  await shotAs(page, "cp28-clip-card");

  await card.getByTestId("clip-play").click();
  await expect.poll(plays).toBeGreaterThan(0);
  const caption = card.getByTestId("clip-caption");
  await expect(caption).toBeVisible();
  const lines = await card.getByTestId("lines").locator("p").allTextContents();
  expect(lines).toContain(await caption.textContent());
  await shotAs(page, "cp28-clip-playing");
  // The still and the captions came from Nura's own server; no video site — the publisher's
  // or any platform's — was asked for anything. (The app's own typeface comes from its font
  // host, as on every screen; blob: pictures have no host.)
  const clipAsks = asked.filter((url) => /\/feed\/[^/]+\/clip\/(poster|captions)$/.test(new URL(url).pathname));
  expect(clipAsks.some((url) => url.endsWith("/clip/poster")) && clipAsks.some((url) => url.endsWith("/clip/captions"))).toBe(true);
  expect(clipAsks.filter((url) => !NURA.has(new URL(url).host))).toEqual([]);
  expect([...hosts].filter((host) => VIDEO_SITES.test(host))).toEqual([]);
  // What he did goes back on the next connection: opened, and a play, and nothing measures
  // how long a card was on his screen.
  const flushed = page.waitForRequest((asked) => asked.method() === "POST" && asked.url().endsWith("/feed/events"));
  await page.getByTestId("pager").evaluate((el) => el.scrollBy({ top: el.clientHeight }));
  const sent = (await flushed).postDataJSON() as { events: { event: string; seconds: number | null }[] };
  for (const one of sent.events) {
    expect(["opened", "played", "replayed", "asked_more", "shared"]).toContain(one.event);
    if (one.event === "opened") expect(one.seconds).toBeNull();
  }
});

test("his week in 30 seconds: his own numbers over the still, no boundary, no link", async ({ page, request }) => {
  await captureSpeech(page);
  const pa = await seedFeed(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await openFeed(page);
  await pageUntil(page, "recap");
  const card = page.locator("article.feed-card[data-type=recap]").first();
  await expect(card.locator("h2.title")).toHaveText("Your week, in 30 seconds");
  await expect(card.getByTestId("lines").locator("p").first()).toHaveText("This is your week, from your blood pressure book.");
  await expect(card.getByTestId("clip-poster")).toBeVisible();
  await expect(card.getByTestId("boundary")).toHaveCount(0);
  await expect(card.getByTestId("watch-whole")).toHaveCount(0);
  await shotAs(page, "cp28-recap");
});

test.describe("the caregiver density at 360 by 640", () => {
  test.use({ viewport: { width: 360, height: 640 } });

  test("the chief's Home: Watching for Pa with sources and how often, pause and add; Sent to Pa this week with what became of each card, counting nothing", async ({ page, request }) => {
    const family = await seedFamily(request);
    await readingsFor(request, family);
    await signIn(page, family.mei, false);
    await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
    const watching = page.getByTestId("watching");
    await expect(watching.locator("h2")).toHaveText("Watching for Pa");
    const explainer = watching.getByTestId("watch").filter({ has: page.getByTestId("watch-label").getByText("Blood pressure, in simple words", { exact: true }) });
    await expect(explainer.getByTestId("watch-meta")).toContainText("HealthHub");
    await expect(explainer.getByTestId("watch-meta")).toContainText("When something new comes in");
    await expect(watching).toContainText("Nura reads only health offices, hospitals and doctors' groups.");
    // Pause, and start again.
    await explainer.getByTestId("watch-toggle").click();
    await expect(explainer).toHaveAttribute("data-enabled", "false");
    await expect(explainer.getByTestId("watch-meta")).toContainText("Paused");
    await explainer.getByTestId("watch-toggle").click();
    await expect(explainer).toHaveAttribute("data-enabled", "true");
    // She adds a watch: festive food, weekly by its kind. Ramadan is not hers to add — whether
    // he fasts is his to say, on his own Me page.
    await watching.getByTestId("watch-add").click();
    await expect(watching.getByTestId("watch-add-fasting-month")).toHaveCount(0);
    await watching.getByTestId("watch-add-festive-food").click();
    await expect(watching.getByTestId("watch-added")).toHaveText("Nura will watch for this from now on.");
    const festive = watching.getByTestId("watch").filter({ has: page.getByText("Festive food, before it comes", { exact: true }) });
    await expect(festive.getByTestId("watch-meta")).toContainText("Every week");
    await shotAs(page, "cp28-watching");

    const sent = page.getByTestId("sent");
    await expect(sent.locator("h2")).toHaveText("Sent to Pa this week");
    const rows = sent.getByTestId("sent-item");
    await expect(rows.first()).toBeVisible();
    // What became of each card, in the catalogue's words; never the now card, the gate or hers.
    for (const type of await rows.evaluateAll((all) => all.map((row) => (row as HTMLElement).dataset.type))) {
      expect(["now", "gate", "duty"]).not.toContain(type);
    }
    await expect(sent.getByTestId("sent-status").first()).toHaveText(/^(This was on the page Pa sees\.|Pa opened this card\.|Pa heard this card\.|Nura kept this back from Pa\.)$/);
    // The NHCS clip is a watch's find, but its only words are the compressor's free text, with
    // no *_THEIRS twin to say them about him by name (#210) — it is silently left off her list,
    // the same as the backend's own week-accounting test (test_feed_formats.py) now asserts.
    await expect(rows.filter({ hasText: "Your blood pressure, in 30 seconds" })).toHaveCount(0);
    await shotAs(page, "cp28-sent");
  });

  test("the ask bar's filters: Records, Web, Providers, Videos — the web and videos from the allowlist only", async ({ page, request }) => {
    const family = await seedFamily(request);
    await readingsFor(request, family);
    await signIn(page, family.mei, false);
    await page.getByTestId("open-ask").click();
    const filters = page.getByTestId("ask-filters");
    await expect(filters.locator("button")).toHaveText(["Your papers", "Online", "Doctors and clinics", "Videos"]);
    await page.getByTestId("filter-web").click();
    await expect(page.getByTestId("filter-web")).toHaveAttribute("aria-pressed", "true");
    await page.getByLabel("Your question").fill("blood pressure");
    await page.getByTestId("ask-send").click();
    const found = page.getByTestId("found");
    await expect(found.first()).toBeVisible();
    for (const href of await page.getByTestId("found-link").evaluateAll((all) => all.map((a) => (a as HTMLAnchorElement).href))) {
      expect(href).toMatch(/^https:\/\/www\.(healthhub\.sg|nhcs\.com\.sg)\//);
    }
    await expect(found.first().getByTestId("boundary")).toBeVisible();
    await shotAs(page, "cp28-find-web");
    await page.getByTestId("filter-videos").click();
    await page.getByTestId("ask-send").click();
    await expect(page.getByTestId("found-link").first()).toHaveText("Watch the whole video at National Heart Centre Singapore");
    await page.getByTestId("filter-providers").click();
    await page.getByLabel("Your question").fill("tan");
    await page.getByTestId("ask-send").click();
    await expect(page.getByTestId("found-nothing")).toHaveText("Nura found nothing for this.");
  });
});

test("his town and Ramadan on Me, on his yes; his chief reads his town and cannot set it or add Ramadan; his own ask bar is his records only", async ({ page, request }) => {
  const family = await seedFamily(request);
  await signIn(page, family.pa, true);
  await page.getByTestId("open-ask").click();
  await expect(page.getByTestId("ask-filters")).toHaveCount(0);
  // Me is a sheet the header's avatar opens (D1), on every screen, rather than a tab.
  await openMe(page);
  const area = page.getByTestId("area");
  await expect(area.locator("h2")).toHaveText("Where you live");
  await expect(area.getByTestId("area-now")).toHaveText("Nura does not know your town.");
  await area.getByTestId("area-change").click();
  await area.getByTestId("area-choice").filter({ hasText: /^Bedok$/ }).click();
  await expect(area.getByTestId("area-ask")).toHaveText("Do you live in Bedok?");
  await area.getByTestId("area-yes").click();
  await expect(area.getByTestId("area-now")).toHaveText("Nura knows your town is Bedok.");
  await expect(area).toContainText("The one who looks after your papers can see your town.");
  await shotAs(page, "cp28-area");
  // Ramadan, on his own yes; the screen says his chief will see it too.
  const ramadan = page.getByTestId("ramadan");
  await expect(ramadan).toContainText("The one who looks after your papers will see this too.");
  await ramadan.getByTestId("ramadan-yes").click();
  await expect(ramadan.getByTestId("ramadan-on")).toHaveText("Nura will tell you before Ramadan.");
  const theirs = await request.post(`${API}/profiles/${family.profileId}/search-jobs`, { headers: auth(family.mei.token), data: { kind: "seasonal", terms: ["fasting month"] } });
  expect(theirs.status()).toBe(403);
  const hers = await request.get(`${API}/profiles/${family.profileId}/area`, { headers: auth(family.mei.token) });
  expect(await hers.json()).toMatchObject({ area: "Bedok", may_set: false });
  const refused = await request.put(`${API}/profiles/${family.profileId}/area`, { headers: auth(family.mei.token), data: { area: "Toa Payoh" } });
  expect(refused.status()).toBe(403);
});
