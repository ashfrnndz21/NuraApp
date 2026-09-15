import { devices, expect, test, type APIRequestContext, type Page, type Request } from "@playwright/test";
import { BASE_URL, FROZEN_CLOCK } from "../../playwright.config";
import {
  API,
  apiToken,
  backendClock,
  captureSpeech,
  CONSULT_BYTES,
  fakeRecorder,
  fixClock,
  freshPhone,
  nothingDrawnOverLines,
  seedFeed,
  seedMedicine,
  seedVisitDay,
  shotAs,
  signInThroughTheApp,
  stand,
} from "./helpers";

/** Checkpoint 27's web half (W7): the patient's day on a phone-sized screen, against `make dev`
 *  serving the build, both clocks at 10 in the morning in Singapore on Monday 14 September. Every
 *  line checked here is compared with what the backend answered, in its order: the phone writes
 *  no sentence. The not-feeling-well paths assert request order, and a lost network never leaves
 *  him with nothing. */

test.beforeAll(async ({ request }) => {
  const backend = await backendClock(request);
  if (!backend.frozen || Date.parse(backend.now) !== Date.parse(FROZEN_CLOCK)) {
    throw new Error(`the backend's clock is not frozen at ${FROZEN_CLOCK} (it says ${JSON.stringify(backend)})`);
  }
});

test.beforeEach(async ({ page }) => {
  await fixClock(page);
  await captureSpeech(page);
});

interface Line {
  id: string;
  text: string;
}
interface WhatToDo {
  kind: string;
  lines: Line[];
  flag_id: string | null;
  check_in_at: string | null;
  notified_person_ids: string[];
  by_voice: boolean;
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });
const texts = (lines: Line[]) => lines.map((line) => line.text);
const voice = (label: string) => [...Buffer.from(`nura-voice-placeholder:${label}\n`)];
const isApi = (sent: Request) => new URL(sent.url()).pathname.startsWith("/api/");
const posted = (path: RegExp) => (sent: { request(): Request } | Request) => {
  const req = "request" in sent && typeof sent.request === "function" ? sent.request() : (sent as Request);
  return req.method() === "POST" && path.test(new URL(req.url()).pathname);
};
/** No control over a line, and every button 56 by 56 (the patient density): #118's hit test. */
const nothingCovers = (page: Page) =>
  nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label, blockquote", controls: "button", minTarget: 56 });
const whatToDoLines = (page: Page) => page.getByTestId("what-to-do-lines").locator("p");

/** A demo deployment (ADR 0008): the banner first on every screen. */
async function showDemoBanner(page: Page): Promise<void> {
  await page.route("**/api/deployment", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ region: "SG", demo: true }) }),
  );
}

/** With the demo banner shown, the what-to-do card never sits under it: at the top of the page
 *  every line is below the banner and is what the page hits at its centre. */
async function notUnderTheBanner(page: Page): Promise<string[]> {
  await expect(page.locator(".demo-banner")).toBeVisible();
  return page.evaluate(() => {
    window.scrollTo(0, 0);
    const bottom = document.querySelector(".demo-banner")?.getBoundingClientRect().bottom ?? 0;
    const problems: string[] = [];
    for (const line of document.querySelectorAll<HTMLElement>("[data-testid=what-to-do-lines] p")) {
      const box = line.getBoundingClientRect();
      if (box.top < bottom) problems.push(`under the banner: ${line.textContent}`);
      if (box.bottom > window.innerHeight) continue;
      const at = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      if (!(at === line || (at !== null && line.contains(at)))) problems.push(`covered: ${line.textContent}`);
    }
    return problems;
  });
}

/** Every /api request the page makes, with its order, for the red-flag paths. */
function apiTrail(page: Page): { log: { at: number; kind: "start" | "end"; method: string; path: string; req: Request }[]; inflight: () => number } {
  const log: { at: number; kind: "start" | "end"; method: string; path: string; req: Request }[] = [];
  let open = 0;
  let n = 0;
  page.on("request", (sent) => {
    if (!isApi(sent)) return;
    open += 1;
    log.push({ at: n++, kind: "start", method: sent.method(), path: new URL(sent.url()).pathname, req: sent });
  });
  const done = (sent: Request) => {
    if (!isApi(sent)) return;
    open -= 1;
    log.push({ at: n++, kind: "end", method: sent.method(), path: new URL(sent.url()).pathname, req: sent });
  };
  page.on("requestfinished", done);
  page.on("requestfailed", done);
  return { log, inflight: () => open };
}

/** Pa with his own papers only, opened on the API: the app lands on Today at sign-in. */
async function ownProfile(request: APIRequestContext): Promise<{ phone: string; token: string; profileId: string }> {
  const phone = freshPhone("+659666");
  const token = await apiToken(request, phone);
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    ...auth(token),
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  return { phone, token, profileId: ((await opened.json()) as { profile_id: string }).profile_id };
}

/** Delete what the phone kept of the offline cards, as if it had never read them. */
async function forgetOfflineCards(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      new Promise<number>((done) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const tx = opened.result.transaction("kv", "readwrite");
          const store = tx.objectStore("kv");
          let gone = 0;
          const keys = store.getAllKeys();
          keys.onsuccess = () => {
            for (const key of keys.result) {
              if (String(key).startsWith("nfw.")) {
                store.delete(key);
                gone += 1;
              }
            }
          };
          tx.oncomplete = () => done(gone);
        };
        opened.onerror = () => done(-1);
      }),
  );
}

// --- E13-02: the button -------------------------------------------------------------------------

test("not feeling well, typed: the backend's card, every line in its order — Mei told, a check-in in two hours", async ({ page, request }) => {
  await showDemoBanner(page);
  const pa = await seedVisitDay(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("not-well").click();
  await expect(page.getByTestId("not-well-ask")).toContainText("Say it or type it in your own words.");
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-not-well", true);

  await page.getByTestId("not-well-words").fill("tired today");
  const answered = page.waitForResponse(posted(/\/not-feeling-well$/));
  await page.getByTestId("not-well-send").click();
  const card = (await (await answered).json()) as WhatToDo;
  expect(card.kind).toBe("rest");
  expect(card.flag_id).toBeNull();
  expect(card.check_in_at).not.toBeNull();
  expect(card.notified_person_ids).toContain(pa.meiId);
  expect(texts(card.lines).slice(0, 4)).toEqual(["Mei knows now.", "Sit down and rest now.", "Mei will call you today.", "Nura will ask you again in 2 hours."]);
  // The screen is the backend's lines, all of them, in its order.
  await expect(whatToDoLines(page)).toHaveText(texts(card.lines));
  await expect(page.getByTestId("offline-note")).toHaveCount(0);
  expect(await nothingCovers(page)).toEqual([]);
  expect(await notUnderTheBanner(page)).toEqual([]);
  await shotAs(page, "cp27-rest-card", true);
});

test("a red word said out loud: the flag first, the urgent card as sent, and the wash cross-fades to act", async ({ page, request }) => {
  await fakeRecorder(page, voice("chest-pain"));
  await page.addInitScript(() => {
    const runs: string[] = [];
    (window as unknown as { __washRuns: string[] }).__washRuns = runs;
    document.addEventListener(
      "transitionrun",
      (event) => {
        if (event.target === document.documentElement) runs.push((event as TransitionEvent).propertyName);
      },
      true,
    );
  });
  await showDemoBanner(page);
  const pa = await seedVisitDay(request);
  const trail = apiTrail(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("not-well")).toBeVisible();
  await page.getByTestId("not-well").click();
  await page.getByTestId("not-well-say").click();
  await expect(page.getByTestId("red-dot")).toBeVisible();
  // Nothing of Today's reads still on the wire: the next request is his.
  await expect.poll(trail.inflight).toBe(0);
  const mark = trail.log.length;
  const answered = page.waitForResponse(posted(/\/not-feeling-well$/));
  await page.getByTestId("not-well-stop").click();
  const card = (await (await answered).json()) as WhatToDo;
  // His voice note is the first thing sent, and it comes back as the urgent card.
  expect(trail.log.slice(mark).find((entry) => entry.kind === "start")).toMatchObject({ method: "POST", path: `/api/profiles/${pa.profileId}/not-feeling-well` });
  expect(card.kind).toBe("red_flag");
  expect(card.by_voice).toBe(true);
  expect(card.flag_id).toBeTruthy();
  const urgent = ["Mei knows now.", "Call the ambulance now on 995.", "After that, call Mei.", "Nura does not decide what is wrong."];
  expect(texts(card.lines)).toEqual(urgent);
  await expect(whatToDoLines(page)).toHaveText(urgent);
  expect(await nothingCovers(page)).toEqual([]);
  expect(await notUnderTheBanner(page)).toEqual([]);
  await shotAs(page, "cp27-urgent-card", true);

  // Back on Today, State says act: the wash cross-fades (E15-01), on the typed stops.
  await page.getByTestId("back-today").click();
  await expect(page.locator("html")).toHaveAttribute("data-posture", "act");
  await expect.poll(() => page.evaluate(() => (window as unknown as { __washRuns: string[] }).__washRuns)).toContain("--wash-a");
  await expect
    .poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--wash-a").trim()), { timeout: 5000 })
    .toBe("rgb(240, 214, 210)");
});

// --- E17-01, E17-02: the feeling cloud ------------------------------------------------------------

test("a red word on the cloud reaches the flag before any other request, the ladder is written, and the strip goes", async ({ page, request }) => {
  await showDemoBanner(page);
  const pa = await seedVisitDay(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const trail = apiTrail(page);
  await signInThroughTheApp(page, pa.phone, "Pa");
  const cloud = page.getByTestId("feeling-cloud");
  await expect(cloud).toContainText("How are you feeling today?");
  await expect(cloud.getByTestId("feeling-word").first()).toHaveText("Dizzy");
  expect(await nothingDrawnOverLines(cloud, { lines: "p", controls: "button", minTarget: 56 })).toEqual([]);
  await shotAs(page, "cp27-cloud", true);
  await expect.poll(trail.inflight).toBe(0);

  const mark = trail.log.length;
  const answered = page.waitForResponse(posted(/\/feelings$/));
  await cloud.locator('[data-word="chest_tightness"]').click();
  const felt = (await (await answered).json()) as { red_flag: boolean; flag_id: string; escalation_id: string; told: string[]; card: WhatToDo };
  await expect(whatToDoLines(page)).toHaveText(texts(felt.card.lines));
  expect(await nothingCovers(page)).toEqual([]);
  expect(await notUnderTheBanner(page)).toEqual([]);

  // The order: the tap is the first request after it, and no other request completes before it.
  const after = trail.log.slice(mark);
  const flag = after.find((entry) => entry.kind === "start")!;
  expect(flag).toMatchObject({ method: "POST", path: `/api/profiles/${pa.profileId}/feelings` });
  const flagDone = after.findIndex((entry) => entry.kind === "end" && entry.req === flag.req);
  expect(after.slice(0, flagDone).filter((entry) => entry.kind === "end")).toEqual([]);
  expect(felt.red_flag).toBe(true);
  expect(felt.flag_id).toBeTruthy();
  expect(felt.told).toContain(pa.meiId);
  expect(texts(felt.card.lines)).toEqual(["Mei knows now.", "Call the ambulance now on 995.", "After that, call Mei.", "Nura does not decide what is wrong."]);

  // The ladder the flag started is the one delivery climbs (E11, ADR 0005).
  expect(felt.escalation_id).toBeTruthy();
  const ran = await request.post(`${API}/dev/run-triggers`, { data: { profile_id: pa.profileId } });
  expect(ran.ok()).toBe(true);
  const deliveries = (await (await request.get(`${API}/profiles/${pa.profileId}/deliveries`, auth(pa.token))).json()) as { ladder_id: string | null; trigger_type: string }[];
  expect(deliveries.some((row) => row.ladder_id === felt.escalation_id && row.trigger_type === "flag")).toBe(true);

  // Today again: act, and the strip is gone until State changes again.
  await page.getByTestId("back-today").click();
  await expect(page.locator("html")).toHaveAttribute("data-posture", "act");
  await expect(page.getByTestId("not-well")).toBeVisible();
  await expect(page.getByTestId("feeling-cloud")).toHaveCount(0);
});

test("a word, its one question, and the note kept for the visit — the strip goes after the tap", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  await signInThroughTheApp(page, pa.phone, "Pa");
  const cloud = page.getByTestId("feeling-cloud");
  const tapped = page.waitForResponse(posted(/\/feelings$/));
  await cloud.locator('[data-word="dizzy"]').click();
  const felt = (await (await tapped).json()) as { red_flag: boolean; question: { words: string; answers: { answer: string; label: string }[] } };
  expect(felt.red_flag).toBe(false);
  const question = page.getByTestId("feeling-question");
  await expect(question.locator("h1")).toHaveText(felt.question.words);
  await expect(question.locator("button:not([data-testid=hear])")).toHaveText(felt.question.answers.map((one) => one.label));
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-question", true);

  const answered = page.waitForResponse(posted(/\/feelings\/[^/]+\/answer$/));
  await page.getByTestId("answer-yesterday").click();
  const done = (await (await answered).json()) as { note: { headline: string; lines: string[]; then: string; boundary: string } };
  const note = page.getByTestId("feeling-note");
  await expect(note.locator("h1")).toHaveText(done.note.headline);
  await expect(note.getByTestId("note-lines").locator("p")).toHaveText([...done.note.lines, done.note.then]);
  await expect(note.getByTestId("boundary").locator("p")).toHaveText(done.note.boundary.split("\n"));
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-note", true);

  await page.getByTestId("back-today").click();
  await expect(page.getByTestId("not-well")).toBeVisible();
  await expect(page.getByTestId("reading-prompt")).toBeVisible();
  await expect(page.getByTestId("feeling-cloud")).toHaveCount(0);
});

test("no network on a red word: the backend's offline card the phone kept — and with none kept, the same words built in; never nothing", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const keptRead = page.waitForResponse((response) => response.url().includes("/not-feeling-well/offline") && response.ok());
  await signInThroughTheApp(page, pa.phone, "Pa");
  await keptRead;
  const offline = (await (await request.get(`${API}/profiles/${pa.profileId}/not-feeling-well/offline?language=en`, auth(pa.token))).json()) as { red_flag: Line[]; unknown: Line[] };

  await page.route("**/api/profiles/*/feelings", (route) => route.abort("internetdisconnected"));
  await page.getByTestId("feeling-cloud").locator('[data-word="chest_tightness"]').click();
  await expect(page.getByTestId("what-to-do-screen")).toHaveAttribute("data-offline", "network");
  await expect(page.getByTestId("offline-note")).toHaveText("Nura cannot reach the internet right now.");
  await expect(whatToDoLines(page)).toHaveText(texts(offline.red_flag));
  expect(texts(offline.red_flag)).toContain("Nura could not send this to your family.");
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-offline-kept", true);

  // Nothing kept, and the offline cards cannot be read either: the catalogue's copy.
  expect(await forgetOfflineCards(page)).toBe(1);
  await page.route("**/api/profiles/*/not-feeling-well/offline*", (route) => route.abort("internetdisconnected"));
  await page.getByTestId("back-today").click();
  await page.getByTestId("feeling-cloud").locator('[data-word="chest_tightness"]').click();
  await expect(whatToDoLines(page)).toHaveText([
    "You did right to say so.",
    "Nura could not send this to your family.",
    "Call the ambulance now on 995.",
    "Nura does not decide what is wrong.",
  ]);

  // The button with no network: whatever he typed, the offline card for the button.
  await page.route("**/api/profiles/*/not-feeling-well", (route) => route.abort("internetdisconnected"));
  await page.getByTestId("back-today").click();
  await page.getByTestId("not-well").click();
  await page.getByTestId("not-well-words").fill("chest pain");
  await page.getByTestId("not-well-send").click();
  await expect(whatToDoLines(page)).toHaveText([
    "You did right to say so.",
    "Nura could not send this to your family.",
    "Call your family now.",
    "If you feel very bad, call the ambulance now on 995.",
    "Nura does not decide what is wrong.",
  ]);
  // Nothing reached the backend: no flag, no symptom.
  const log = (await (await request.get(`${API}/profiles/${pa.profileId}/symptoms`, auth(pa.token))).json()) as { entries: unknown[] };
  expect(log.entries).toEqual([]);
});

test("a red word that hangs rather than fails: at the deadline the offline card the phone kept, never a page that waits", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const keptRead = page.waitForResponse((response) => response.url().includes("/not-feeling-well/offline") && response.ok());
  await signInThroughTheApp(page, pa.phone, "Pa");
  await keptRead;
  const offline = (await (await request.get(`${API}/profiles/${pa.profileId}/not-feeling-well/offline?language=en`, auth(pa.token))).json()) as { red_flag: Line[] };
  // The connection is up and the server never answers: the request is left hanging.
  await page.route("**/api/profiles/*/feelings", () => undefined);
  await page.getByTestId("feeling-cloud").locator('[data-word="chest_tightness"]').click();
  await expect(page.getByTestId("what-to-do-screen")).toHaveCount(0);
  await page.clock.fastForward("00:11");
  await expect(page.getByTestId("what-to-do-screen")).toHaveAttribute("data-offline", "network");
  await expect(whatToDoLines(page)).toHaveText(texts(offline.red_flag));
});

test("an answer that makes the word red, not sent: the red card; any other answer not sent keeps the question, said in one sentence", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  await seedMedicine(request, pa.token, pa.profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 30 });
  const keptRead = page.waitForResponse((response) => response.url().includes("/not-feeling-well/offline") && response.ok());
  await signInThroughTheApp(page, pa.phone, "Pa");
  await keptRead;
  const offline = (await (await request.get(`${API}/profiles/${pa.profileId}/not-feeling-well/offline?language=en`, auth(pa.token))).json()) as { red_flag: Line[] };
  const tapped = page.waitForResponse(posted(/\/feelings$/));
  await page.getByTestId("feeling-cloud").locator('[data-word="breathless"]').click();
  const felt = (await (await tapped).json()) as { question: { follow_up: string; answers: { answer: string; red: boolean }[] } };
  expect(felt.question.follow_up).toBe("at_rest");
  expect(felt.question.answers.map((one) => [one.answer, one.red])).toEqual([["yes", true], ["no", false]]);
  await page.route("**/api/profiles/*/feelings/*/answer", (route) => route.abort("internetdisconnected"));
  // "No" not sent: the question stays, and one sentence says why.
  await page.getByTestId("answer-no").click();
  await expect(page.getByTestId("notice")).toContainText("Nura");
  await expect(page.getByTestId("feeling-question")).toBeVisible();
  // "Yes" — breathless even sitting still — not sent: the red card, never less.
  await page.getByTestId("answer-yes").click();
  await expect(page.getByTestId("what-to-do-screen")).toHaveAttribute("data-offline", "network");
  await expect(whatToDoLines(page)).toHaveText(texts(offline.red_flag));
  expect(await nothingCovers(page)).toEqual([]);
});

// --- E14-01: symptoms -----------------------------------------------------------------------------

test("a red word in the symptom log: the backend's urgent card is what he sees next", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-symptoms").click();
  await page.getByTestId("symptom-words").fill("chest pain since this morning");
  const logged = page.waitForResponse(posted(/\/symptoms$/));
  await page.getByTestId("symptom-keep").click();
  const body = (await (await logged).json()) as { flag_id: string; card: Line[] };
  expect(body.flag_id).toBeTruthy();
  expect(texts(body.card)).toEqual(["Mei knows now.", "Call the ambulance now on 995.", "After that, call Mei.", "Nura does not decide what is wrong."]);
  await expect(whatToDoLines(page)).toHaveText(texts(body.card));
  await expect(page.getByTestId("what-to-do-screen")).toHaveAttribute("data-offline", "no");
  expect(await nothingCovers(page)).toEqual([]);
});


test("a symptom said out loud, with how much and since when; Mei reads it in plain words on her phone", async ({ page, browser, request }) => {
  await fakeRecorder(page, voice("dizzy-quite-a-lot"));
  const pa = await seedVisitDay(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-symptoms").click();
  await expect(page.getByTestId("symptom-ask")).toContainText("Say what you feel, how bad it is and since when.");
  expect(await nothingCovers(page)).toEqual([]);
  await page.getByTestId("symptom-say").click();
  const logged = page.waitForResponse(posted(/\/symptoms$/));
  await page.getByTestId("symptom-stop").click();
  const entry = ((await (await logged).json()) as { entry: { lines: Line[]; severity: number; duration: string; by_voice: boolean } }).entry;
  expect(entry).toMatchObject({ severity: 2, duration: "this_morning", by_voice: true });
  const said = ["Pa felt dizzy on Monday 14 September.", "It was quite bad.", "It started this morning.", "Pa said this out loud."];
  expect(texts(entry.lines)).toEqual(said);
  await expect(page.getByTestId("symptom-saved")).toContainText("Nura wrote this down.");
  await expect(page.getByTestId("symptom-saved").locator(".lines p")).toHaveText(said);
  await expect(page.getByTestId("symptom-log-lines")).toContainText(said[0]!);
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-symptoms", true);

  // Mei, his chief, on her own phone: the same lines, in the backend's plain words.
  const hers = await browser.newContext({ ...devices["Pixel 5"], baseURL: BASE_URL, timezoneId: "Asia/Singapore", serviceWorkers: "allow" });
  const mei = await hers.newPage();
  await fixClock(mei);
  await signInThroughTheApp(mei, pa.meiPhone, "Mei");
  await mei.getByTestId("door-key").first().click();
  await mei.getByTestId("open-symptoms").click();
  await expect(mei.getByRole("heading", { name: "How Pa has felt" })).toBeVisible();
  const read = mei.getByTestId("symptom-log-lines");
  for (const line of said) await expect(read).toContainText(line);
  await hers.close();
});

// --- E05-01, E05-02: the brief and the questions ----------------------------------------------------

test("the visit: the whole brief in its order, and his questions added and taken off on his yes", async ({ page, request }) => {
  const pa = await seedVisitDay(request);
  const visit = `${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}`;
  const brief = (await (await request.get(`${visit}/brief`, auth(pa.token))).json()) as { lines: { section: string; text: string }[]; boundary: string };
  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();
  await page.getByTestId("open-brief").click();
  const body = brief.lines.filter((line) => line.section !== "boundary");
  await expect(page.getByTestId("brief-lines").locator("p")).toHaveText(body.map((line) => line.text));
  await expect(page.getByTestId("brief").getByTestId("boundary").locator("p")).toHaveText(brief.boundary.split("\n"));
  expect(body.map((line) => line.section)).toContain("purpose");
  expect(body.map((line) => line.section)).toContain("bring");
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-brief", true);

  await page.getByRole("button", { name: "Go back" }).click();
  await page.getByTestId("open-questions").click();
  const before = (await (await request.get(`${visit}/questions`, auth(pa.token))).json()) as { card: string[] };
  await expect(page.getByTestId("question-card").locator(".lines p")).toHaveText(before.card);
  expect(await nothingCovers(page)).toEqual([]);

  // A question in his words, kept on his yes to exactly those words.
  const mine = "Is the water pill bad for my kidneys?";
  await page.getByTestId("question-words").fill(mine);
  await page.getByTestId("question-add-button").click();
  await expect(page.getByTestId("question-check")).toContainText("Is this what you want to ask?");
  await expect(page.getByTestId("question-typed")).toHaveText(mine);
  expect(await nothingCovers(page)).toEqual([]);
  await page.getByTestId("question-yes").click();
  await expect(page.getByTestId("said")).toHaveText("Nura kept your question.");
  await expect(page.getByTestId("question-line").filter({ hasText: mine })).toHaveCount(1);
  const kept = (await (await request.get(`${visit}/questions`, auth(pa.token))).json()) as { questions: { text: string; source: string }[]; card: string[] };
  expect(kept.questions.find((one) => one.text === mine)?.source).toBe("person");
  await expect(page.getByTestId("question-card").locator(".lines p")).toHaveText(kept.card);
  await shotAs(page, "cp27-questions", true);

  // Words that are not plain are refused by the backend, in its words.
  await page.getByTestId("question-words").fill("only the part for you");
  await page.getByTestId("question-add-button").click();
  await page.getByTestId("question-yes").click();
  await expect(page.getByTestId("notice")).toHaveText("Please write the question in plain words.");

  // Taken off, on his yes to exactly that.
  await page.getByTestId("question-line").filter({ hasText: mine }).getByTestId("question-remove").click();
  await expect(page.getByTestId("question-remove-check")).toContainText("Take this question off your list?");
  await page.getByTestId("question-remove-yes").click();
  await expect(page.getByTestId("said")).toHaveText("Nura took the question off your list.");
  await expect(page.getByTestId("question-line").filter({ hasText: mine })).toHaveCount(0);
});

// --- E05-05, E21-03: the post-visit card on the web, and its clips on his feed -----------------------

/** The card across the pager's middle. */
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
  for (let n = 0; n < 20; n++) {
    if ((await onScreen(page)) === type) return;
    const before = await pager.evaluate((el) => el.scrollTop);
    await page.locator("article.feed-card").first().focus();
    await pager.evaluate((el) => el.scrollBy({ top: el.clientHeight }));
    await expect.poll(() => pager.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
  }
  throw new Error(`no ${type} card within 20 cards`);
}

test("the post-visit card on the web: each line with where it was said, one left out, his yes, the memo card; the dose change stays a question; the memo card's clips", async ({ page, request }) => {
  await fakeRecorder(page);
  const pa = await seedVisitDay(request, { recording: true });
  const visit = `${API}/profiles/${pa.profileId}/appointments/${pa.appointmentId}`;
  const upload = await request.post(`${visit}/recording?duration_s=66.4`, {
    headers: { Authorization: `Bearer ${pa.meiToken}`, "Content-Type": "audio/webm;codecs=opus" },
    data: Buffer.from(CONSULT_BYTES),
  });
  expect(upload.status()).toBe(201);
  const summary = ((await upload.json()) as { summary: { summary_id: string; lines: string[]; boundary: string; items: { item_id: string; text: string; kind: string }[] } }).summary;
  const boundary = summary.boundary.split("\n");
  const body = summary.lines.slice(0, summary.lines.length - boundary.length);

  await signInThroughTheApp(page, pa.phone, "Pa");
  await page.getByTestId("open-visit").click();
  await expect(page.getByTestId("summary-waiting")).toHaveText("This card is waiting for your yes.");
  const lines = page.getByTestId("summary-line");
  await expect(lines.locator("> p")).toHaveText(body);
  await expect(page.getByTestId("summary").getByTestId("boundary").locator("p")).toHaveText(boundary);
  // Where each thing was said: the stretch of the recording, under its line.
  const water = lines.filter({ hasText: "water pill" });
  await expect(water.locator("> p")).toHaveText("Ask Dr Tan about the new amount of the water pill (frusemide).");
  await expect(water.getByTestId("hear-clip")).toHaveText("Hear what Dr Tan said");
  // A dose change is a question for the doctor: no line says an amount to take.
  for (const line of body) expect(line).not.toMatch(/\b\d+(\.\d+)?\s?(mg|tablets?|pills?)\b/i);

  // He leaves one out, and says yes to the rest.
  const weigh = summary.items.find((item) => /weigh|scale/i.test(item.text))!;
  const weighLine = page.locator(`[data-testid=summary-line][data-item-id="${weigh.item_id}"]`);
  await weighLine.getByTestId("leave-out").click();
  await expect(weighLine.getByTestId("leave-out")).toHaveAttribute("aria-pressed", "true");
  await expect(weighLine.getByTestId("left-out")).toHaveText("Nura will leave this out.");
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-summary", true);
  await page.getByTestId("summary-yes").click();
  await expect(page.getByTestId("summary-kept")).toHaveText("Nura kept what Dr Tan said.");
  const memos = (await (await request.get(`${API}/profiles/${pa.profileId}/memos`, auth(pa.token))).json()) as { card: string[]; memos: { text: string }[] };
  await expect(page.getByTestId("memo-lines").locator("p")).toHaveText(memos.card);
  expect(memos.memos.map((memo) => memo.text)).not.toContain(weigh.text);
  await expect(page.getByTestId("summary-yes")).toHaveCount(0);
  expect(await nothingCovers(page)).toEqual([]);
  await shotAs(page, "cp27-memo-card", true);

  // What his yes wrote: the left-out item rejected, a flag for the dose change, a planned follow-up.
  const cards = (await (await request.get(`${visit}/summaries`, auth(pa.token))).json()) as { summary_id: string; confirmed_at: string | null; items: { item_id: string; kind: string; state: string; flag_id: string | null }[] }[];
  const closed = cards.find((card) => card.summary_id === summary.summary_id)!;
  expect(closed.confirmed_at).not.toBeNull();
  expect(closed.items.find((item) => item.item_id === weigh.item_id)?.state).toBe("rejected");
  expect(closed.items.find((item) => item.kind === "medication_change")?.flag_id).toBeTruthy();

  // E21-03: the memo card on his feed, each line with the stretch it was said in, played on a tap.
  // Today reads its own page first; then the pager's fresh first page — the one with the memo
  // card made since — is waited for, never raced: a page that lands after he has scrolled is
  // merged in below the card on screen (`feed/store.ts`), and the test does not depend on when.
  const isFeedPage = (response: { request(): { method(): string }; url(): string }) => response.request().method() === "GET" && /\/profiles\/[^/]+\/feed$/.test(new URL(response.url()).pathname);
  const todays = page.waitForResponse(isFeedPage);
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await todays;
  const fresh = page.waitForResponse(isFeedPage);
  await page.getByTestId("open-feed").click();
  await fresh;
  await expect(page.getByTestId("pager")).toBeVisible();
  await expect(page.locator("article.feed-card").first()).toBeVisible();
  await pageUntil(page, "memo");
  const memo = page.locator("article.feed-card[data-type=memo]").first();
  const withClip = memo.getByTestId("card-line").filter({ has: page.getByTestId("hear-clip") }).first();
  const caption = (await withClip.locator("> p").textContent())!;
  expect((await stand(page)).__clips).toEqual([]);
  await withClip.getByTestId("hear-clip").click();
  await expect.poll(async () => (await stand(page)).__clips.length).toBe(1);
  expect((await stand(page)).__clips[0]).toMatch(/^blob:.*#t=\d+(\.\d)?,\d+(\.\d)?$/);
  // The one player (E15-07): its transcript is the card's own line while the stretch plays.
  await expect(withClip.getByTestId("player-line")).toHaveText(caption);
  await shotAs(page, "cp27-feed-clip");

  // A recording this key may not hear: the backend's refusal in words, never an empty player.
  await page.route("**/api/profiles/*/artifacts/*/clip*", (route) =>
    route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ refusal: "OnlyTheFamilyHears" }) }),
  );
  // Out of the feed and back: the feed opens with a player that has fetched nothing yet.
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await page.getByTestId("open-feed").click();
  await expect(page.locator("article.feed-card").first()).toBeVisible();
  await pageUntil(page, "memo");
  // The same line, by its words: once refused, it has no button to be found by.
  const again = page.locator("article.feed-card[data-type=memo]").first().getByTestId("card-line").filter({ hasText: caption }).first();
  await again.getByTestId("hear-clip").click();
  await expect(again.getByTestId("clip-refused")).toHaveText("Only the owner and the family he let in can hear this.");
  await expect(again.getByTestId("hear-clip")).toHaveCount(0);
});

// --- E11-07, E17-04, E11-02: the nudge, the proud number on Me, today's top three -------------------

test("the day's nudge where the backend plans it, with its why: OK, and it is gone; the proud number on Me in his words", async ({ page, request }) => {
  const pa = await ownProfile(request);
  const plan = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges/plan`, auth(pa.token))).json()) as { drafts: { kind: string; lines: string[]; why: string }[] };
  const draft = plan.drafts[0]!;
  expect(draft.kind).not.toBe("check_in");
  await signInThroughTheApp(page, pa.phone, "Pa");
  const nudge = page.getByTestId("nudge");
  await expect(nudge.getByTestId("nudge-lines").locator("p")).toHaveText(draft.lines);
  await expect(nudge.getByTestId("nudge-why")).toHaveText(draft.why);
  await expect(nudge.getByTestId("nudge-accept")).toHaveText(draft.kind === "commitment" ? "It went well" : "OK");
  await expect(nudge.getByTestId("nudge-dismiss")).toHaveText("Not today");
  expect(await nothingDrawnOverLines(nudge, { lines: "p", controls: "button", minTarget: 56 })).toEqual([]);
  await shotAs(page, "cp27-nudge", true);

  const handed = page.waitForResponse(posted(/\/nudges\/plan$/));
  const answered = page.waitForResponse(posted(/\/nudges\/[^/]+\/response$/));
  await nudge.getByTestId("nudge-accept").click();
  expect((await handed).status()).toBe(201);
  expect((await answered).request().postDataJSON()).toEqual({ kind: "accepted" });
  await expect(page.getByTestId("nudge")).toHaveCount(0);
  const day = (await (await request.get(`${API}/profiles/${pa.profileId}/nudges`, auth(pa.token))).json()) as { nudges: { lines: string[]; responses: string[] }[] };
  expect(day.nudges).toHaveLength(1);
  expect(day.nudges[0]).toMatchObject({ lines: draft.lines, responses: ["accepted"] });
  // Opened again: the page restores the session and reads the doors once (`afterSignIn`), then
  // lands on Today; the answered nudge does not come back.
  const doors = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/doors");
  await page.reload();
  await doors;
  await expect(page.getByTestId("not-well")).toBeVisible();
  await expect(page.getByTestId("nudge")).toHaveCount(0);

  // Me: the number that only goes up, as the backend says it.
  const summary = (await (await request.get(`${API}/profiles/${pa.profileId}/me-summary?language=en`, auth(pa.token))).json()) as { proud_days: number; lines: string[] };
  await expect(async () => {
    await page.getByRole("button", { name: "Me", exact: true }).click();
    await expect(page.getByTestId("me-proud-number")).toBeVisible({ timeout: 2000 });
  }).toPass();
  await expect(page.getByTestId("me-proud-number")).toHaveText(String(summary.proud_days));
  await expect(page.getByTestId("me-proud-lines").locator("p")).toHaveText(summary.lines);
  expect(summary.lines).toContain("This number only goes up.");
  for (const line of summary.lines) expect(line).not.toMatch(/streak|in a row|missed/i);
  expect(await nothingDrawnOverLines(page.getByTestId("me-proud"), { lines: "p", controls: "button", minTarget: 56 })).toEqual([]);
  await shotAs(page, "cp27-me", true);
});

test("today's top three: one card a screen with Next, in the backend's order, each under its why", async ({ page, request }) => {
  const pa = await seedFeed(request);
  const top = ((await (await request.get(`${API}/profiles/${pa.profileId}/feed/today`, auth(pa.token))).json()) as { items: { headline: string; status: string; why: { plain?: string } }[] }).items.filter(
    (item) => item.status !== "dismissed",
  );
  expect(top.length).toBeGreaterThan(0);
  await signInThroughTheApp(page, pa.phone, "Pa");
  const three = page.getByTestId("top-three");
  await expect(three).toHaveAttribute("data-count", String(top.length));
  for (const [at, item] of top.entries()) {
    await expect(three).toHaveAttribute("data-at", String(at));
    await expect(three.getByTestId("top-three-card")).toHaveCount(1);
    await expect(three.getByTestId("top-three-card")).toContainText(item.headline);
    if (item.why.plain) await expect(three.getByTestId("top-three-card").locator(".provenance")).toHaveText(item.why.plain);
    expect(await nothingDrawnOverLines(three, { lines: "h2, p", controls: "button", minTarget: 56 })).toEqual([]);
    if (at < top.length - 1) await three.getByTestId("top-three-next").click();
  }
  await expect(three.getByTestId("top-three-next")).toHaveCount(0);
  await shotAs(page, "cp27-top-three", true);
});

// --- E15-01: the wash ------------------------------------------------------------------------------

test("the wash cross-fades when State changes, and with Reduce Motion the new wash is simply there", async ({ page, request }) => {
  await page.addInitScript(() => {
    const runs: string[] = [];
    (window as unknown as { __washRuns: string[] }).__washRuns = runs;
    document.addEventListener("transitionrun", (event) => {
      if (event.target === document.documentElement) runs.push((event as TransitionEvent).propertyName);
    }, true);
  });
  const pa = await ownProfile(request);
  await signInThroughTheApp(page, pa.phone, "Pa");
  await expect(page.getByTestId("not-well")).toBeVisible();
  const runs = () => page.evaluate(() => (window as unknown as { __washRuns: string[] }).__washRuns.splice(0));
  const stop = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--wash-a").trim());
  await runs();

  await page.evaluate(() => (document.documentElement.dataset.posture = "watch"));
  await expect.poll(async () => (await page.evaluate(() => (window as unknown as { __washRuns: string[] }).__washRuns))).toEqual(expect.arrayContaining(["--wash-a", "--wash-b", "--wash-c"]));
  const moving = await page.evaluate(() =>
    document.documentElement.getAnimations().map((each) => ({ property: (each as CSSTransition).transitionProperty, duration: each.effect?.getTiming().duration })),
  );
  expect(moving).toEqual(expect.arrayContaining([{ property: "--wash-a", duration: 1200 }]));
  await expect.poll(stop, { timeout: 5000 }).toBe("rgb(241, 220, 230)");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await runs();
  await page.evaluate(() => (document.documentElement.dataset.posture = "act"));
  expect(await stop()).toBe("rgb(240, 214, 210)");
  expect(await page.evaluate(() => document.documentElement.getAnimations().length)).toBe(0);
  expect(await runs()).toEqual([]);
});
