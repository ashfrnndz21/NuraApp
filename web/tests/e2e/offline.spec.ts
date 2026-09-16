import { expect, test, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import {
  API,
  apiToken,
  breakfastAt,
  expireKeptPages,
  fixClock,
  freshPhone,
  medicinesInIndexedDb,
  seedMedicine,
  shot,
  signInThroughTheApp,
  todayReady,
  openMe,
  cutKey,
  keptKeys,
  seedOwner,
  waitForWorker, expectProud} from "./helpers";

test.beforeEach(async ({ page }) => {
  await fixClock(page);
});

/** With the network gone, the app opens on the page the phone kept: the service worker serves
 *  the shell, IndexedDB holds today's page under the key that read it, and the page says when
 *  it was read. It is today's list, not a Now card — a kept page cannot know what is due — and
 *  there is no Taken and no spinner. Past the local midnight the kept page is deleted and only
 *  the emergency card (kept past midnight, dated: ADR 0010) and one line show: no dose from old
 *  data. */
test("offline: the kept page as a dated list with no Taken; past midnight only the emergency card", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const phone = freshPhone();
  const token = await apiToken(request, phone);
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  await seedMedicine(request, token, profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 });

  await signInThroughTheApp(page, phone, "Pa");
  await todayReady(page);
  await expect.poll(async () => (await medicinesInIndexedDb(page)).length).toBeGreaterThan(0);
  // Today reads the emergency card after it has kept its page: wait for both before the network goes.
  await expect.poll(async () => (await keptKeys(page)).some((key) => key.startsWith("emergency."))).toBe(true);
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((done) => navigator.serviceWorker.addEventListener("controllerchange", () => done(), { once: true }));
    }
  });

  await context.setOffline(true);
  await page.reload();
  const offline = page.getByTestId("offline");
  await expect(offline).toContainText("Nura cannot reach the internet right now.");
  await expect(offline).toContainText("This is your Today page from earlier.");
  await expect(offline).toContainText(/Nura last read your papers on [A-Z][a-z]+day \d{1,2} [A-Z][a-z]+ at \d{1,2}:\d{2}\s?[ap]m\./);
  const list = page.getByTestId("today-list");
  await expect(list).toContainText("Your tablets for today");
  await expect(list).toContainText("Take 1 tablet of your blood pressure tablet with breakfast.");
  await expect(list).toContainText("This comes from your Today page.");
  await expect(page.getByTestId("now-card")).toHaveCount(0);
  await expect(page.getByTestId("missed-card")).toHaveCount(0);
  await expect(page.getByTestId("taken")).toHaveCount(0);
  // Both clocks stand at 10:00 (the backend's is frozen for the run), so the kept page carries
  // the feed's cards for today, and they stand in "For you today" in place of the State card.
  await expect(page.getByTestId("feed-card").first()).toContainText("Your tablets today");
  await expect(page.getByTestId("state-card")).toHaveCount(0);
  // The proud number on Me is the kept page's own count (D1).
  await openMe(page);
  await expect(page.getByTestId("proud-number")).toBeVisible();
  await page.getByTestId("sheet-close").click();
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await shot(page, "offline-kept");

  // The next morning, still offline: the kept page is past its midnight.
  expect(await expireKeptPages(page)).toBe(1);
  await page.reload();
  await expect(page.getByTestId("cannot-reach")).toContainText("Nura cannot reach your papers right now.");
  await expect(page.getByTestId("emergency-card")).toContainText("Emergency card");
  await expect(page.getByTestId("emergency-card")).toContainText("This is Pa's emergency card.");
  await expect(page.getByTestId("emergency-read")).toContainText("Nura last read this card on Monday 14 September.");
  for (const gone of ["today-list", "now-card", "taken", "state-card", "medicines-card", "proud", "offline", "reading-prompt", "emergency-placeholder", "hero-figure"]) {
    await expect(page.getByTestId(gone)).toHaveCount(0);
  }
  expect(await medicinesInIndexedDb(page)).toEqual([]);
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await shot(page, "offline-expired");
  await context.setOffline(false);
});

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

/** Every POST …/taken the phone got an answer to: the line, what it sent, and the status. */
function answeredTaps(page: Page): { line: string; body: { anchor?: string; taken_at?: string }; status: number }[] {
  const seen: { line: string; body: { anchor?: string; taken_at?: string }; status: number }[] = [];
  page.on("response", (response) => {
    const sent = response.request();
    const found = new URL(response.url()).pathname.match(/\/medicines\/([^/]+)\/taken$/);
    if (sent.method() === "POST" && found) seen.push({ line: found[1]!, body: sent.postDataJSON() as { anchor?: string; taken_at?: string }, status: response.status() });
  });
  return seen;
}

/** E00-08: Taken tapped with no network is held on the phone with the moment he tapped, shown as
 *  held, kept across a reload, and sent once each, in the order he tapped, when the network is
 *  back; the backend writes each once, at that moment, and the page reads again. */
test("Taken with no network: held with the moment he tapped, then sent once each, in order, when the network is back", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const pa = await seedOwner(request, "Pa", [
    { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 },
    { generic: "atorvastatin", strength: "20 mg", dose_text: "1 tab QDS", quantity: 120 },
  ]);
  // Two tablets on the same anchor, so that tapping the first leaves a second to tap: this
  // test is about the order they are sent in, so it needs both due at once.
  await breakfastAt(request, pa.token, pa.profileId);
  const taps = answeredTaps(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  // A tile per dose due (D1, the design's card grammar), so this walks the first of them.
  const now = page.getByTestId("now-card").first();
  await expect(now.getByTestId("taken")).toBeVisible();
  const first = (await now.locator("h2").textContent())!;
  await waitForWorker(page);

  await context.setOffline(true);
  await now.getByTestId("taken").click();
  const held = page.getByTestId("held-card");
  await expect(held).toHaveCount(1);
  await expect(held.first().locator("h2")).toHaveText(first);
  await expect(held.first()).toContainText(/You tapped this at (half past )?\d{1,2}(\.\d{2})? in the morning\./);
  await expect(held.first()).toContainText("Nura will send what you tapped when the internet is back.");
  // The next dose the backend marked due is the Now card, with its own Taken.
  await expect(now.locator("h2")).not.toHaveText(first);
  const second = (await now.locator("h2").textContent())!;
  await now.getByTestId("taken").click();
  await expect(held).toHaveCount(2);
  expect(taps).toEqual([]);

  // Held on the phone across a reload with no network, and said.
  await page.reload();
  await expect(page.getByTestId("held")).toContainText("Nura will send what you tapped when the internet is back.");
  expect((await keptKeys(page)).some((key) => key.startsWith("queue."))).toBe(true);

  // The network is back: each sent once, oldest first, with the moment he tapped.
  await context.setOffline(false);
  await expect(page.getByTestId("held-sent")).toContainText("Nura sent what you tapped.");
  expect(taps.map((tap) => tap.status)).toEqual([201, 201]);
  for (const tap of taps) expect(tap.body.taken_at).toMatch(/^2026-09-14T02:0\d:\d\d\.\d{3}Z$/);
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as {
    line_id: string;
    name: string;
    count: { taken: number } | null;
  }[];
  const nameOf = (id: string) => lines.find((line) => line.line_id === id)!.name.toLowerCase();
  expect(taps.map((tap) => nameOf(tap.line))).toEqual([first.toLowerCase(), second.toLowerCase()]);
  expect(lines.map((line) => line.count?.taken)).toEqual([1, 1]);
  await expectProud(page, "1"); // the proud number is on the Me sheet (D1)
  await expect(page.getByTestId("held-card")).toHaveCount(0);

  // Offline and back again, and a reload: nothing is sent twice, nothing is left held.
  await context.setOffline(true);
  await context.setOffline(false);
  await page.reload();
  await expectProud(page, "1"); // the proud number is on the Me sheet (D1)
  expect(taps).toHaveLength(2);
  expect((await keptKeys(page)).some((key) => key.startsWith("queue."))).toBe(false);
});

/** A Taken the backend wrote whose answer never reached the phone (the network lost on the way
 *  back): the phone holds it with the moment it sent, sends it again with that same moment, and
 *  the backend finds the row it already wrote — the tablet is counted once, not twice. */
test("Taken whose answer is lost on the way back: held, sent again with the same moment, and counted once", async ({ page, request }) => {
  const pa = await seedOwner(request, "Pa", [{ generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 }]);
  await breakfastAt(request, pa.token, pa.profileId);
  const sent: { taken_at?: string }[] = [];
  page.on("request", (call) => {
    if (call.method() === "POST" && /\/medicines\/[^/]+\/taken$/.test(new URL(call.url()).pathname)) sent.push(call.postDataJSON() as { taken_at?: string });
  });
  await signInThroughTheApp(page, pa.phone, "Pa");
  // A tile per dose due (D1, the design's card grammar), so this walks the first of them.
  const now = page.getByTestId("now-card").first();
  await expect(now.getByTestId("taken")).toBeVisible();

  // The first Taken reaches the backend and is written; its answer is lost before the phone.
  const taken = /\/medicines\/[^/]+\/taken$/;
  await page.route(taken, async (route) => {
    await route.fetch();
    await route.abort("internetdisconnected");
  });
  await now.getByTestId("taken").click();
  await expect(page.getByTestId("held-card")).toHaveCount(1);
  const count = async () =>
    ((await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as { count: { taken: number } | null }[])[0]!.count?.taken;
  expect(await count()).toBe(1);

  // The page read again: the held tap goes with the moment the first one carried, and the
  // backend answers with the row it wrote.
  await page.unroute(taken);
  await page.reload();
  await expect(page.getByTestId("held-sent")).toContainText("Nura sent what you tapped.");
  await expect(page.getByTestId("held-card")).toHaveCount(0);
  expect(sent).toHaveLength(2);
  expect(sent[0]!.taken_at).toMatch(/^2026-09-14T/);
  expect(sent[1]!.taken_at).toBe(sent[0]!.taken_at);
  expect(await count()).toBe(1);
  await expectProud(page, "1"); // the proud number is on the Me sheet (D1)
});

/** A held tap the backend says no to — here, Mei's key was closed while her phone was offline —
 *  is said in the backend's words for that no, and nothing of Pa's papers stays on her phone. */
test("a no to a held tap is said in the backend's words, and nothing of the papers stays", async ({ page, context, request }) => {
  const pa = await seedOwner(request);
  await breakfastAt(request, pa.token, pa.profileId);
  const mei = await cutKey(request, pa, { name: "Mei", prefix: "+659557" }, "caregiver", ["medicines", "records", "emergency"]);
  const taps = answeredTaps(page);
  await signInThroughTheApp(page, mei.phone, "Mei");
  await page.getByTestId("door-key").click();
  // A tile per dose due (D1, the design's card grammar), so this walks the first of them.
  const now = page.getByTestId("now-card").first();
  await expect(now.getByTestId("taken")).toBeVisible();

  await context.setOffline(true);
  await now.getByTestId("taken").click();
  await expect(page.getByTestId("held-card")).toHaveCount(1);
  const closed = await request.delete(`${API}/profiles/${pa.profileId}/keys/${mei.keyId}`, auth(pa.token));
  expect(closed.ok(), await closed.text()).toBe(true);

  await context.setOffline(false);
  await expect(page.getByTestId("held-refused")).toContainText("You cannot see these papers any more.");
  expect(taps.map((tap) => tap.status)).toEqual([403]);
  expect(taps[0]!.body.taken_at).toMatch(/^2026-09-14T/);
  // The held tap's no is said first; then the page is read again, refused, and the phone's copy
  // goes — wait for that, not for the sentence.
  await expect.poll(() => medicinesInIndexedDb(page, { card: true })).toEqual([]);
  await expect.poll(async () => (await keptKeys(page)).filter((key) => /^(today|feed|queue|emergency)\./.test(key))).toEqual([]);
  // The backend wrote nothing for the tap it said no to.
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as { count: { taken: number } | null }[];
  expect(lines[0]!.count?.taken).toBe(0);
});

/** Move the not-feeling-well cards the phone kept (ADR 0012) past their midnight. */
async function expireOfflineCards(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const tx = opened.result.transaction("kv", "readwrite");
          let moved = 0;
          const cursor = tx.objectStore("kv").openCursor();
          cursor.onsuccess = () => {
            const at = cursor.result;
            if (!at) return;
            if (typeof at.key === "string" && at.key.startsWith("nfw.")) {
              at.update({ ...(at.value as object), expiresAt: "2000-01-01T00:00:00.000Z" });
              moved += 1;
            }
            at.continue();
          };
          tx.oncomplete = () => resolve(moved);
        };
        opened.onerror = () => resolve(-1);
      }),
  );
}

/** The not-feeling-well cards (ADR 0012) under the phone's rules for what it keeps (E00-08):
 *  read with Today and kept; served with no network when the app opens again from the home
 *  screen; gone at the region's midnight, when the same words built in stand in — never
 *  nothing; and gone at sign-out. */
test("the not-feeling-well cards on the phone: served with no network after a reopen, gone at the region's midnight and at sign-out, never nothing", async ({ page, context, request }) => {
  test.skip(BASE_URL.includes(":5173"), "needs the built app the backend serves (the worker is not built in dev)");
  const pa = await seedOwner(request);
  const read = page.waitForResponse((response) => response.url().includes("/not-feeling-well/offline") && response.ok());
  await signInThroughTheApp(page, pa.phone, "Pa");
  await read;
  const cards = (await (await request.get(`${API}/profiles/${pa.profileId}/not-feeling-well/offline?language=en`, auth(pa.token))).json()) as { unknown: { text: string }[] };
  await expect.poll(async () => (await keptKeys(page)).some((key) => key.startsWith("nfw."))).toBe(true);
  await expect.poll(async () => (await keptKeys(page)).some((key) => key.startsWith("emergency."))).toBe(true);
  await waitForWorker(page);
  const notWell = async () => {
    await page.getByTestId("not-well").click();
    await page.getByTestId("not-well-words").fill("chest pain");
    await page.getByTestId("not-well-send").click();
  };

  // No network, the app opened again from the home screen: the button answers with the card the phone kept.
  await context.setOffline(true);
  await page.reload();
  await notWell();
  await expect(page.getByTestId("offline-note")).toHaveText("Nura cannot reach the internet right now.");
  await expect(page.getByTestId("what-to-do-lines").locator("p")).toHaveText(cards.unknown.map((line) => line.text));

  // The next morning, still offline: the kept cards are past their midnight and gone, and the
  // button says the same words built in.
  await page.getByTestId("back-today").click();
  expect(await expireOfflineCards(page)).toBe(1);
  await page.reload();
  await expect(page.getByTestId("not-well")).toBeVisible();
  await notWell();
  await expect(page.getByTestId("what-to-do-lines").locator("p")).toHaveText([
    "You did right to say so.",
    "Nura could not send this to your family.",
    "Call your family now.",
    "If you feel very bad, call the ambulance now on 995.",
    "Nura does not decide what is wrong.",
  ]);
  expect((await keptKeys(page)).some((key) => key.startsWith("nfw."))).toBe(false);
  await context.setOffline(false);

  // Back online Today reads them again; sign-out leaves none of it on the phone.
  await page.reload();
  await todayReady(page);
  await expect.poll(async () => (await keptKeys(page)).some((key) => key.startsWith("nfw."))).toBe(true);
  await page.getByRole("button", { name: "Me", exact: true }).click();
  await page.getByTestId("sign-out").click();
  await expect(page.getByLabel("Your phone number")).toBeVisible();
  expect((await keptKeys(page)).filter((key) => /^(today|feed|queue|emergency|nfw)\./.test(key))).toEqual([]);
});

/** An owner closing his account (#151): from then on nobody opens his papers, him included, so
 *  nothing of them stays on the phone either — the Today page, the feed, the emergency card
 *  (which outlives midnight, ADR 0010), the not-feeling-well cards and any held tap go the
 *  moment he says yes, and the doors say why; opened again, the app still keeps none of them. */
test("an account closing: nothing of its papers stays on the phone, and the doors say why", async ({ page, request }) => {
  const pa = await seedOwner(request);
  const kept = async () => (await keptKeys(page)).filter((key) => key.endsWith(pa.profileId));
  await signInThroughTheApp(page, pa.phone, "Pa");
  await todayReady(page);
  await expect.poll(async () => (await kept()).some((key) => key.startsWith("emergency."))).toBe(true);
  await expect.poll(async () => (await kept()).some((key) => key.startsWith("nfw."))).toBe(true);
  expect((await kept()).some((key) => key.startsWith("today."))).toBe(true);

  await page.getByTestId("tab-family").click();
  await page.getByTestId("open-consents").click();
  await page.getByTestId("consent").filter({ hasText: "Nura keeps your papers" }).getByTestId("close-account").click();
  await page.getByTestId("close-yes").click();
  await expect(page.getByTestId("notice")).toContainText("Nura has stopped keeping these papers.");
  await expect.poll(kept).toEqual([]);
  expect((await request.get(`${API}/profiles/${pa.profileId}`, auth(pa.token))).status()).toBe(403);

  await page.reload();
  await expect(page.getByTestId("notice")).toContainText("Nura has stopped keeping these papers.");
  expect(await kept()).toEqual([]);
});
