import { expect, test, type Page } from "@playwright/test";
import { BASE_URL } from "../../playwright.config";
import {
  API,
  apiToken,
  cutKey,
  expireKeptPages,
  fixClock,
  freshPhone,
  keptKeys,
  medicinesInIndexedDb,
  seedMedicine,
  seedOwner,
  shot,
  signInThroughTheApp,
  waitForWorker,
} from "./helpers";

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
  await expect(page.getByTestId("proud")).toBeVisible();
  await expect.poll(async () => (await medicinesInIndexedDb(page)).length).toBeGreaterThan(0);
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
  await expect(page.getByTestId("proud-number")).toBeVisible();
  expect(await page.locator("[role=progressbar], .spinner").count()).toBe(0);
  await shot(page, "offline-kept");

  // The next morning, still offline: the kept page is past its midnight.
  expect(await expireKeptPages(page)).toBe(1);
  await page.reload();
  await expect(page.getByTestId("cannot-reach")).toContainText("Nura cannot reach your papers right now.");
  await expect(page.getByTestId("emergency-card")).toContainText("Emergency card");
  await expect(page.getByTestId("emergency-card")).toContainText("This is Pa's emergency card.");
  await expect(page.getByTestId("emergency-read")).toContainText(/Nura read this card on Monday 14 September at \d{1,2}:\d{2}\s?[ap]m\./);
  for (const gone of ["today-list", "now-card", "taken", "state-card", "medicines-card", "proud", "offline", "reading-prompt", "emergency-placeholder"]) {
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
  const taps = answeredTaps(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  const now = page.getByTestId("now-card");
  await expect(now.getByTestId("taken")).toBeVisible();
  const first = (await now.locator("h2").textContent())!;
  await waitForWorker(page);

  await context.setOffline(true);
  await now.getByTestId("taken").click();
  const held = page.getByTestId("held-card");
  await expect(held).toHaveCount(1);
  await expect(held.first().locator("h2")).toHaveText(first);
  await expect(held.first()).toContainText(/You tapped this at \d{1,2}:\d{2}\s?am\./);
  await expect(held.first()).toContainText("Nura will send it when the internet is back.");
  // The next dose the backend marked due is the Now card, with its own Taken.
  await expect(now.locator("h2")).not.toHaveText(first);
  const second = (await now.locator("h2").textContent())!;
  await now.getByTestId("taken").click();
  await expect(held).toHaveCount(2);
  expect(taps).toEqual([]);

  // Held on the phone across a reload with no network, and said.
  await page.reload();
  await expect(page.getByTestId("held")).toContainText("Nura will send it when the internet is back.");
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
  await expect(page.getByTestId("proud-number")).toHaveText("1");
  await expect(page.getByTestId("held-card")).toHaveCount(0);

  // Offline and back again, and a reload: nothing is sent twice, nothing is left held.
  await context.setOffline(true);
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByTestId("proud-number")).toHaveText("1");
  expect(taps).toHaveLength(2);
  expect((await keptKeys(page)).some((key) => key.startsWith("queue."))).toBe(false);
});

/** A held tap the backend says no to — here, Mei's key was closed while her phone was offline —
 *  is said in the backend's words for that no, and nothing of Pa's papers stays on her phone. */
test("a no to a held tap is said in the backend's words, and nothing of the papers stays", async ({ page, context, request }) => {
  const pa = await seedOwner(request);
  const mei = await cutKey(request, pa, { name: "Mei", prefix: "+659557" }, "caregiver", ["medicines", "records", "emergency"]);
  const taps = answeredTaps(page);
  await signInThroughTheApp(page, mei.phone, "Mei");
  await page.getByTestId("door-key").click();
  const now = page.getByTestId("now-card");
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
  expect(await medicinesInIndexedDb(page, { card: true })).toEqual([]);
  expect((await keptKeys(page)).filter((key) => /^(today|feed|queue|emergency)\./.test(key))).toEqual([]);
  // The backend wrote nothing for the tap it said no to.
  const lines = (await (await request.get(`${API}/profiles/${pa.profileId}/medicines?language=en`, auth(pa.token))).json()) as { count: { taken: number } | null }[];
  expect(lines[0]!.count?.taken).toBe(0);
});
