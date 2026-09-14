import { expect, test, type APIRequestContext } from "@playwright/test";
import { API, apiToken, captureSpeech, freshPhone, medicinesInIndexedDb, seedMedicine, shot, signInThroughTheApp } from "./helpers";

interface Slot {
  line_id: string;
  anchor: string;
  taken: boolean;
  due_now: boolean;
  missed: boolean;
  if_forgotten: string[];
  source: string;
}
interface FeedItem {
  supply: string;
  status: string;
  headline: string;
  why: { plain?: string };
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

async function todaySlots(request: APIRequestContext, token: string, profileId: string): Promise<Slot[]> {
  return (await (await request.get(`${API}/profiles/${profileId}/medicines/today?language=en`, auth(token))).json()) as Slot[];
}

/** The feed's cards for "For you today", as the app reads them: its first two now and today
 *  cards. In the quiet hours (21:00–07:00 on his wall clock) there are none. */
async function forYouFromFeed(request: APIRequestContext, token: string, profileId: string): Promise<FeedItem[]> {
  const page = (await (await request.get(`${API}/profiles/${profileId}/feed`, auth(token))).json()) as { items: FeedItem[] };
  return page.items.filter((item) => item.status !== "dismissed" && (item.supply === "now" || item.supply === "today")).slice(0, 2);
}

/** Checkpoint 10 on a phone-sized screen: sign in with a code from the log, open my own
 *  papers on today's words, see Today, act on exactly what the backend marks due, hear a
 *  card, sign out with nothing left on the phone. */
test("sign in, agree, Today, Taken only when due, Hear, sign out clean", async ({ page, request }) => {
  const phone = freshPhone();
  await captureSpeech(page);
  await signInThroughTheApp(page, phone, "Pa");

  await page.getByTestId("door-for-me").click();
  const words = page.getByTestId("consent-words");
  await expect(words).toContainText("Nura keeps your papers, your medicines and your blood pressure book.");
  await expect(words).toContainText("They never leave Singapore.");
  await page.getByTestId("agree").click();

  await expect(page.getByTestId("no-medicines")).toContainText("Nura has no medicines for you yet.");
  await expect(page.getByTestId("proud-number")).toHaveText("0");
  await expect(page.locator("html")).toHaveAttribute("data-density", "patient");
  await expect(page.locator("html")).toHaveAttribute("data-posture", "stable");
  const token = await apiToken(request, phone);
  const me = (await (await request.get(`${API}/me`, auth(token))).json()) as { profile_id: string };
  if ((await forYouFromFeed(request, token, me.profile_id)).length === 0) {
    await expect(page.getByTestId("state-card")).toContainText("Your day is steady.");
    // The boundary is the backend's own line on the State, never a client string.
    const boundary = ((await (await request.get(`${API}/profiles/${me.profile_id}/state`, auth(token))).json()) as { boundary: string }).boundary;
    for (const line of boundary.split("\n")) await expect(page.getByTestId("state-card").getByTestId("boundary")).toContainText(line);
    await expect(page.getByTestId("state-card")).toContainText("Nura worked this out on");
  }

  // Four doses a day, so that at almost any hour the backend marks one due or one missed.
  await seedMedicine(request, token, me.profile_id, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 });
  const slots = await todaySlots(request, token, me.profile_id);
  const due = slots.find((slot) => slot.due_now);
  const missed = slots.find((slot) => slot.missed && !slot.taken);
  const fromFeed = await forYouFromFeed(request, token, me.profile_id);
  await page.reload();

  if (fromFeed.length > 0) {
    // The feed carries today's cards: its first two, in its order, each under its own why.
    const cards = page.getByTestId("feed-card");
    await expect(cards).toHaveCount(fromFeed.length);
    await expect(cards.first()).toContainText(fromFeed[0]!.headline);
    if (fromFeed[0]!.why.plain) await expect(cards.first()).toContainText(fromFeed[0]!.why.plain);
    await expect(page.getByTestId("state-card")).toHaveCount(0);
  } else {
    // No feed cards (the quiet hours, or nothing new): the State and the medicines, in the
    // backend's words, each under its source line.
    await expect(page.getByTestId("state-card").getByTestId("boundary")).toContainText("This is not a doctor's advice.");
    await expect(page.getByTestId("medicines-card")).toContainText("You have 120 tablets of your blood pressure tablet left.");
    await expect(page.getByTestId("medicines-card")).toContainText("This comes from the label you kept on");
  }
  await shot(page, "today");

  if (due) {
    // The Now card is the one the backend marks due: one drug in his words, one whole line,
    // one paper button, the backend's source line, its spoken twin.
    const now = page.getByTestId("now-card");
    await expect(now).toContainText("Your blood pressure tablet");
    await expect(now).toContainText("Take 1 tablet of your blood pressure tablet");
    await expect(now).not.toContainText("amlodipine");
    await expect(now).toContainText(due.source);
    await expect(page.getByTestId("missed-card")).toHaveCount(0);
    const taken = page.getByTestId("taken");
    await expect(taken).toHaveText("Taken");
    expect((await taken.boundingBox())!.height).toBeGreaterThanOrEqual(56);

    expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken)).toEqual([]);
    await now.getByTestId("hear").click();
    const spoken = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
    expect(spoken[0]).toBe("Your blood pressure tablet");
    expect(spoken[1]).toMatch(/^Take 1 tablet of your blood pressure tablet/);

    await taken.click();
    await expect(page.getByText(/^You took it/)).toBeVisible();
    await expect(page.getByTestId("proud-number")).toHaveText("1");
    if (fromFeed.length === 0) {
      await expect(page.getByTestId("medicines-card")).toContainText("You have 119 tablets of your blood pressure tablet left.");
    }
    const after = await todaySlots(request, token, me.profile_id);
    expect(after.filter((slot) => slot.taken).map((slot) => slot.anchor)).toEqual([due.anchor]);
    // Nothing else is offered as "now" unless the backend marks it due; a passed dose shows
    // the story's lines and no Taken.
    if (!after.find((slot) => slot.due_now)) await expect(page.getByTestId("taken")).toHaveCount(0);
    const stillMissed = after.find((slot) => slot.missed && !slot.taken);
    if (stillMissed) await expect(page.getByTestId("missed-card")).toContainText("Never take 2 at once.");
  } else if (missed) {
    await expect(page.getByTestId("taken")).toHaveCount(0);
    const card = page.getByTestId("missed-card");
    await expect(card).toContainText("Your blood pressure tablet");
    await expect(card).toContainText(missed.if_forgotten[0]!);
    await expect(card).toContainText("Never take 2 at once.");
    await expect(card).toContainText(missed.source);
    await expect(page.getByTestId("proud-number")).toHaveText("0");
  } else {
    await expect(page.getByTestId("nothing-now")).toContainText("There is nothing to take right now.");
    await expect(page.getByTestId("taken")).toHaveCount(0);
  }

  // The proud number is the backend's and names its source; no badges; vertical only; the
  // tab bar never covers the last card.
  await expect(page.getByTestId("proud")).toContainText("Nura counted the days you took your tablets.");
  await expect(page.locator("nav.tabbar")).toHaveText(/^\s*Today\s*Me\s*$/);
  const bar = await page.locator("nav.tabbar").boundingBox();
  const viewport = page.viewportSize()!;
  expect(bar!.y + bar!.height).toBeLessThanOrEqual(viewport.height);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const lastCard = await page.locator("main.screen > section").last().boundingBox();
  const barAtBottom = await page.locator("nav.tabbar").boundingBox();
  expect(lastCard!.y + lastCard!.height).toBeLessThanOrEqual(barAtBottom!.y - 8);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    await page.evaluate(() => document.documentElement.clientWidth),
  );

  // The phone holds the page while signed in; after sign-out no medicine remains in IndexedDB.
  expect((await medicinesInIndexedDb(page)).length).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Me" }).click();
  await expect(page.getByText("You are signed in as Pa.")).toBeVisible();
  await page.getByTestId("sign-out").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  expect(await medicinesInIndexedDb(page)).toEqual([]);
  await page.reload();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
});

test("a refused read clears the phone's copy and is said in one plain sentence", async ({ page, request }) => {
  // Pa opens his papers and lets Mei see his medicines and his papers (the State reads under
  // the records scope); Mei signs in on the app and sees Today. Pa closes the key; Mei's next
  // open shows the refusal and keeps nothing.
  const pa = freshPhone();
  const mei = freshPhone("+659666");
  const paToken = await apiToken(request, pa);
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    ...auth(paToken),
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  await seedMedicine(request, paToken, profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 });
  await request.post(`${API}/profiles/${profileId}/consents/sharing`, {
    ...auth(paToken),
    data: { holder_phone_e164: mei, scopes: ["medicines", "records"], relationship: "daughter", language: "en", captured_via: "app" },
  });
  const key = await request.post(`${API}/profiles/${profileId}/keys`, {
    ...auth(paToken),
    data: { holder_phone_e164: mei, role: "caregiver", scopes: ["medicines", "records"] },
  });
  expect(key.status()).toBe(201);
  const keyId = ((await key.json()) as { key_id: string }).key_id;

  await signInThroughTheApp(page, mei, "Mei");
  await page.getByTestId("door-key").click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "caregiver");
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect.poll(async () => (await medicinesInIndexedDb(page)).length).toBeGreaterThan(0);

  await request.delete(`${API}/profiles/${profileId}/keys/${keyId}`, auth(paToken));
  await page.reload();
  const notice = page.getByTestId("notice");
  await expect(notice).toHaveText("You cannot see these papers any more.");
  for (const gone of ["medicines-card", "feed-card", "now-card", "missed-card", "taken", "proud"]) {
    await expect(page.getByTestId(gone)).toHaveCount(0);
  }
  expect(await medicinesInIndexedDb(page)).toEqual([]);
});

test("a key without the records scope opens Today on the medicines and the feed, with no State card", async ({ page, request }) => {
  // Pa lets Siti give him his tablets: her key opens the medicines and nothing else. The
  // State reads under the records scope, so her Today has no State card — and no refusal.
  const pa = freshPhone();
  const siti = freshPhone("+659555");
  const paToken = await apiToken(request, pa);
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    ...auth(paToken),
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  await seedMedicine(request, paToken, profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 });
  await request.post(`${API}/profiles/${profileId}/consents/sharing`, {
    ...auth(paToken),
    data: { holder_phone_e164: siti, scopes: ["medicines"], relationship: "helper", language: "en", captured_via: "app" },
  });
  const key = await request.post(`${API}/profiles/${profileId}/keys`, {
    ...auth(paToken),
    data: { holder_phone_e164: siti, role: "helper", scopes: ["medicines"] },
  });
  expect(key.status()).toBe(201);

  await signInThroughTheApp(page, siti, "Siti");
  await page.getByTestId("door-key").click();
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect(page.locator("[data-testid=medicines-card], [data-testid=feed-card], [data-testid=now-card], [data-testid=missed-card], [data-testid=nothing-now]").first()).toBeVisible();
  await expect(page.getByTestId("state-card")).toHaveCount(0);
  await expect(page.getByTestId("notice")).toHaveCount(0);
  await expect(page.locator("nav.tabbar")).toBeVisible();
});

test("a server error on reopening keeps him on Today, never back at sign-in", async ({ page }) => {
  // What CI met: the page before the reload was still writing its feed cards when the new
  // page asked who he is, and the answer was a 500. The token is still good.
  const phone = freshPhone();
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await expect(page.getByTestId("proud")).toBeVisible();
  let failed = 0;
  await page.route("**/api/me", async (route) => {
    if (failed++ === 0) await route.fulfill({ status: 500, body: "Internal Server Error" });
    else await route.continue();
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Today", exact: true })).toBeVisible();
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect(page.getByLabel("Your phone number")).toHaveCount(0);
  expect(failed).toBeGreaterThan(0);
});

test("a wrong code is one plain sentence, never the class name", async ({ page }) => {
  const phone = freshPhone();
  await page.goto("./");
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByTestId("send-code").click();
  await page.getByLabel("The code").fill("000000");
  await page.getByTestId("verify-code").click();
  const notice = page.getByTestId("notice");
  await expect(notice).toHaveText("That code is not right.");
  await expect(notice).not.toContainText("WrongCode");
});

test("the language picker changes every string and persists on the device", async ({ page }) => {
  const phone = freshPhone();
  await signInThroughTheApp(page, phone, "Pa");
  await page.getByTestId("door-for-me").click();
  await page.getByTestId("agree").click();
  await page.getByRole("button", { name: "Me" }).click();
  await page.getByTestId("lang-ms").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ms");
  await expect(page.getByTestId("sign-out")).toHaveText("Daftar keluar");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "ms");
  await page.getByRole("button", { name: "Hari Ini", exact: true }).click();
  await expect(page.getByTestId("no-medicines")).toContainText("Nura belum ada ubat untuk anda.");
});
