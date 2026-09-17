import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

/** The same three things `backend/scripts/checkpoint.py` does: a fresh number every run, the
 *  login code read from the `make dev` log (never from the API), and a medicine seeded by
 *  the label → OK → write flow so Today has a Now card. */

export const API = process.env.NURA_BASE_URL ?? "http://127.0.0.1:8000";
const HERE = dirname(fileURLToPath(import.meta.url));
const DEV_LOG = process.env.NURA_DEV_LOG ?? resolve(HERE, "../../../backend/.dev.log");
const CODE_LINE = /login code for (\+[0-9]+): ([0-9]{6})/g;

/** The five tabs, in the board's own order and labels (`docs/design/nura-concept-board.html`'s
 *  `.tabbar`, and `web/src/nav.ts`'s `tabsFor`): the one list every spec must check against,
 *  rather than each hand-typing its own — a hand-typed list is the defect that recurred on the
 *  member list, the consent twins and the emergency card (#186, #215), and a tab set is no
 *  different. */
export const TAB_SET = ["Home", "Health", "Connect", "Services", "Profile"] as const;

/** A key cut with only the medicines scope (`nav.ts`'s `NEEDS`): no Connect (needs `family`), no
 *  Services (needs `visits`) — Home and Profile always show. */
export const TAB_SET_MEDICINES_ONLY = ["Home", "Health", "Profile"] as const;

/** A demo deployment (ADR 0008) takes test numbers only (+65 0…) and signs every one in with
 *  the operator's code, which it never prints. With `NURA_E2E_DEMO_CODE` set to that code the
 *  suite walks against a demo: its numbers in the test range, its code instead of the log's. */
const DEMO_CODE = process.env.NURA_E2E_DEMO_CODE;

/** Every number handed out in this run. The run is one worker (`workers: 1`) on one database, so
 *  a repeat would be the same person twice: `409 ProfileAlreadyOwned` when the second test opens
 *  its profile (main's e2e, run 34912734890). Four random digits per prefix give 10,000 numbers,
 *  and a run hands out about a hundred — often enough for two to meet. */
const handedOut = new Set<string>();

/** A stream's body (`ask/stream`, `find/stream`), read back as its events, in the order the
 *  backend sent them (docs/design-direction.md "Conversation, waiting and thinking"): one
 *  `data:` line per event, each real, never invented. */
export function streamedEvents(body: string): { type: string; [key: string]: unknown }[] {
  return body
    .split("\n\n")
    .filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice("data: ".length)) as { type: string; [key: string]: unknown });
}

export function freshPhone(prefix = "+659777"): string {
  for (;;) {
    const phone = DEMO_CODE
      ? `+650${String(Math.floor(Math.random() * 10_000_000)).padStart(7, "0")}`
      : `${prefix}${String(Math.floor(Math.random() * 10000)).padStart(4, "0")}`;
    if (!handedOut.has(phone)) {
      handedOut.add(phone);
      return phone;
    }
  }
}

/** The newest code the server logged for this number, waiting up to five seconds for it. */
export async function codeFromLog(phone: string, after: number): Promise<string> {
  if (DEMO_CODE) return DEMO_CODE;
  const deadline = Date.now() + 5000;
  for (;;) {
    if (existsSync(DEV_LOG)) {
      const text = readFileSync(DEV_LOG, "utf8");
      const codes = [...text.matchAll(CODE_LINE)].filter((m) => m[1] === phone).map((m) => m[2]!);
      if (codes.length > after) return codes[codes.length - 1]!;
    }
    if (Date.now() > deadline) {
      throw new Error(`no login code for ${phone} in ${DEV_LOG}: is the server the one \`make dev\` started?`);
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}

export function codesSoFar(phone: string): number {
  if (DEMO_CODE || !existsSync(DEV_LOG)) return 0;
  return [...readFileSync(DEV_LOG, "utf8").matchAll(CODE_LINE)].filter((m) => m[1] === phone).length;
}

/** Sign in over the API as this number (a second session beside the app's own). */
export async function apiToken(request: APIRequestContext, phone: string): Promise<string> {
  const before = codesSoFar(phone);
  const started = await request.post(`${API}/auth/phone/start`, { data: { phone_e164: phone, language: "en" } });
  if (started.status() !== 202) throw new Error(`start: ${started.status()} ${await started.text()}`);
  const code = await codeFromLog(phone, before);
  const verified = await request.post(`${API}/auth/phone/verify`, { data: { phone_e164: phone, code } });
  if (!verified.ok()) throw new Error(`verify: ${verified.status()} ${await verified.text()}`);
  return ((await verified.json()) as { token: string }).token;
}

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** A label photo, then "what does this label mean", his OK, and the write: one line, 30 tablets. */
export async function seedMedicine(
  request: APIRequestContext,
  token: string,
  profileId: string,
  label: { generic: string; strength: string; dose_text: string; quantity: number },
): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const bytes = Buffer.concat([PNG, Buffer.from(`nura-paper-placeholder:label-${Math.random()}\n`)]);
  const photo = await request.post(`${API}/profiles/${profileId}/photos`, {
    headers,
    data: { data: bytes.toString("base64"), content_type: "image/png", captured_at: "2026-09-14T08:00:00Z" },
  });
  if (photo.status() !== 201) throw new Error(`photo: ${photo.status()} ${await photo.text()}`);
  const artifactId = ((await photo.json()) as { artifact_id: string }).artifact_id;
  const full = { ...label, prescriber: "Dr Tan", source_kind: "retail" };
  const yes = await request.post(`${API}/profiles/${profileId}/confirmations`, {
    headers,
    data: { subject: "medicine", label: full, source_artifact_id: artifactId },
  });
  if (yes.status() !== 201) throw new Error(`confirmation: ${yes.status()} ${await yes.text()}`);
  const confirmationId = ((await yes.json()) as { confirmation_id: string }).confirmation_id;
  const added = await request.post(`${API}/profiles/${profileId}/medicines`, {
    headers,
    data: { label: full, source_artifact_id: artifactId, confirmation_id: confirmationId },
  });
  if (added.status() !== 201) throw new Error(`medicines: ${added.status()} ${await added.text()}`);
  return ((await added.json()) as { line_id: string }).line_id;
}

/** Sign in through the app's own screens: phone → code (from the log) → doors. */
/** Past the welcome a phone shows before its first sign-in (docs/design-direction.md), to the
 *  phone number: Get started when the welcome is there, nothing when this phone has seen it. */
export async function pastWelcome(page: Page): Promise<void> {
  const welcome = page.getByTestId("welcome-screen");
  const phone = page.getByLabel("Your phone number");
  await expect(welcome.or(phone)).toBeVisible();
  if (await welcome.isVisible()) await page.getByTestId("welcome-start").click();
  await expect(phone).toBeVisible();
}

export async function signInThroughTheApp(page: Page, phone: string, name: string): Promise<void> {
  await page.goto("./");
  await pastWelcome(page);
  await page.getByLabel("Your phone number").fill(phone);
  await page.getByLabel("Your name").fill(name);
  const before = codesSoFar(phone);
  await page.getByTestId("send-code").click();
  const code = await codeFromLog(phone, before);
  await page.getByLabel("The code").fill(code);
  await page.getByTestId("verify-code").click();
}

/** Record every utterance instead of speaking it: Playwright's Chromium has no voices. */
export async function captureSpeech(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const spoken: string[] = [];
    const rates: number[] = [];
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    (window as unknown as { __rates: number[] }).__rates = rates;
    (window as unknown as { __cancels: number }).__cancels = 0;
    const synth = {
      // Every stop is counted, so a test can see a voice stop when its card leaves the screen.
      cancel: () => {
        (window as unknown as { __cancels: number }).__cancels += 1;
      },
      speak: (u: { text: string; rate: number }) => {
        spoken.push(u.text);
        rates.push(u.rate);
      },
      speaking: false,
      pending: false,
      paused: false,
      // One voice that runs on the device, so the app speaks; a network-only voice would
      // keep it silent (see speak.ts).
      getVoices: () => [{ lang: "en-SG", localService: true, name: "Local", default: true, voiceURI: "local" }],
      pause: () => undefined,
      resume: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
      onvoiceschanged: null,
    };
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
    // Chromium will not take a made-up voice on a real utterance, so the utterance is a
    // stand-in too: it keeps the text, the voice and the language the app chose.
    class Utterance {
      text: string;
      voice: unknown = null;
      lang = "";
      rate = 1;
      onend: (() => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    }
    Object.defineProperty(window, "SpeechSynthesisUtterance", { value: Utterance, configurable: true });
  });
}

/** The phone's copy of anyone's papers in IndexedDB: every stored value that names a medicine.
 *  The emergency card is left out unless `card` is asked for: it is the one copy the phone keeps
 *  past midnight (docs/adr/0010-offline-taps-and-the-emergency-card.md), checked on its own. */
export async function medicinesInIndexedDb(page: Page, { card = false }: { card?: boolean } = {}): Promise<string[]> {
  return page.evaluate(
    (withCard) =>
      new Promise<string[]>((resolve) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const found: string[] = [];
          const cursor = opened.result.transaction("kv", "readonly").objectStore("kv").openCursor();
          cursor.onsuccess = () => {
            const at = cursor.result;
            if (!at) return resolve(found);
            const text = JSON.stringify(at.value);
            const isCard = String(at.key).startsWith("emergency.");
            if ((withCard || !isCard) && /amlodipine|blood pressure/.test(text)) found.push(text);
            at.continue();
          };
          cursor.onerror = () => resolve(["error"]);
        };
        opened.onerror = () => resolve(["error"]);
      }),
    card,
  );
}

/** Every key the phone keeps in IndexedDB. */
export async function keptKeys(page: Page): Promise<string[]> {
  return page.evaluate(
    () =>
      new Promise<string[]>((resolve) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const all = opened.result.transaction("kv", "readonly").objectStore("kv").getAllKeys();
          all.onsuccess = () => resolve(all.result.map(String));
        };
        opened.onerror = () => resolve([]);
      }),
  );
}

/** Wait until the service worker controls the page, so a reload with no network opens the shell. */
export async function waitForWorker(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((done) => navigator.serviceWorker.addEventListener("controllerchange", () => done(), { once: true }));
    }
  });
}

/** Slow the phone's processor by `rate` (Chromium only): 4 is Lighthouse's mid-tier phone, the
 *  reference for a five-year-old Android. Returns a function that puts it back. */
export async function throttleCpu(page: Page, rate: number): Promise<() => Promise<void>> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate });
  return async () => {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    await cdp.detach();
  };
}

/** A redacted paper the fixture extractor knows, as the bytes it knows it by (backend/tests/paper.py). */
export const paperPhoto = (label: string) => ({ name: `${label}.png`, mimeType: "image/png", buffer: Buffer.concat([PNG, Buffer.from(`nura-paper-placeholder:${label}\n`, "ascii")]) });
export const paperPdf = (label: string) => ({ name: `${label}.pdf`, mimeType: "application/pdf", buffer: Buffer.from(`%PDF-1.4\nnura-paper-placeholder:${label}\n`, "ascii") });

export interface Owner {
  phone: string;
  token: string;
  profileId: string;
}

/** A person with his own papers (today's words agreed over the API) and these medicines, each
 *  written by the label → OK → write flow. `language` (default English) is his own — the one
 *  the app and his emergency card render in; #222/#229's chemical-name-and-strength data is
 *  the register's own words in every one of them, never translated. */
export async function seedOwner(
  request: APIRequestContext,
  name = "Pa",
  medicines: { generic: string; strength: string; dose_text: string; quantity: number }[] = [{ generic: "amlodipine", strength: "5 mg", dose_text: "1 tab QDS", quantity: 120 }],
  language = "en",
): Promise<Owner> {
  const phone = freshPhone("+659666");
  const token = await apiToken(request, phone);
  const words = (await (await request.get(`${API}/consent/wording?language=${language}`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { consent: { wording_version: words.version, language, captured_via: "app" }, display_name: name, language },
  });
  if (opened.status() !== 201) throw new Error(`profile: ${opened.status()} ${await opened.text()}`);
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  for (const label of medicines) await seedMedicine(request, token, profileId, label);
  return { phone, token, profileId };
}

/** Move his breakfast, so that a tablet hanging on it is due at the hour the run is frozen at.
 *  A dose window opens an hour before its anchor and closes an hour after, or at the next
 *  anchor (`app.routines.service.window_of`, E04-02), and the default day puts breakfast at
 *  07:30 — so at the frozen 10:00 the breakfast dose is already missed and nothing is due.
 *  Breakfast at 10:00 opens the window 09:00 to 11:00, which is the plain Taken path: a test
 *  that needs a Taken to tap asks for it here rather than assuming the default day has one. */
export async function breakfastAt(request: APIRequestContext, token: string, profileId: string, at = "10:00"): Promise<void> {
  const set = await request.put(`${API}/profiles/${profileId}/settings`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { language: "en", breakfast_time: at },
  });
  if (!set.ok()) throw new Error(`breakfast: ${set.status()} ${await set.text()}`);
}

/** Let one person in on the owner's own yes (E12) and cut them a key with this role and these
 *  parts: their phone, their token and the key's id. */
export async function cutKey(
  request: APIRequestContext,
  owner: Owner,
  holder: { name: string; prefix: string },
  role: string,
  scopes: string[],
): Promise<{ phone: string; token: string; keyId: string }> {
  const phone = freshPhone(holder.prefix);
  const token = await namedToken(request, phone, holder.name);
  const his = { Authorization: `Bearer ${owner.token}` };
  const letIn = await request.post(`${API}/profiles/${owner.profileId}/consents/sharing`, {
    headers: his,
    data: { holder_phone_e164: phone, holder_display_name: holder.name, scopes, role, window: "always", relationship: "neighbour", language: "en", captured_via: "app" },
  });
  if (letIn.status() !== 201) throw new Error(`sharing: ${letIn.status()} ${await letIn.text()}`);
  const key = await request.post(`${API}/profiles/${owner.profileId}/keys`, { headers: his, data: { holder_phone_e164: phone, role, scopes } });
  if (key.status() !== 201) throw new Error(`key: ${key.status()} ${await key.text()}`);
  return { phone, token, keyId: ((await key.json()) as { key_id: string }).key_id };
}

/** Move every kept Today page past its midnight, the way the next morning finds it. */
export async function expireKeptPages(page: Page): Promise<number> {
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
            if (typeof at.key === "string" && at.key.startsWith("today.")) {
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

/** A full-page screenshot into NURA_SHOTS, when it is set: the operator's checkpoint pictures. */
export async function shot(page: Page, name: string): Promise<void> {
  const dir = process.env.NURA_SHOTS;
  if (!dir) return;
  await page.screenshot({ path: `${dir}/w1-review-${name}.png`, fullPage: true });
}

/** Ten in the morning in Singapore on Monday 14 September. */
export const TEN_AM_IN_SINGAPORE = new Date("2026-09-14T02:00:00Z");

/** Every test that is not about the time runs at the same hour on the phone, whatever the
 *  hour on the runner. What the backend says about the day is read from the backend. */
export async function fixClock(page: Page, at: Date = TEN_AM_IN_SINGAPORE): Promise<void> {
  await page.clock.install({ time: at });
}

/** When the kept Today page expires, as the phone holds it (the first one found). */
export async function keptExpiry(page: Page): Promise<string | null> {
  return page.evaluate(
    () =>
      new Promise<string | null>((resolve) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const cursor = opened.result.transaction("kv", "readonly").objectStore("kv").openCursor();
          cursor.onsuccess = () => {
            const at = cursor.result;
            if (!at) return resolve(null);
            if (typeof at.key === "string" && at.key.startsWith("today.")) return resolve((at.value as { expiresAt: string }).expiresAt);
            at.continue();
          };
        };
        opened.onerror = () => resolve(null);
      }),
  );
}

/** A screenshot under an exact, unique name into NURA_SHOTS, when it is set. */
export async function shotAs(page: Page, file: string, fullPage = false): Promise<string | null> {
  const dir = process.env.NURA_SHOTS;
  if (!dir) return null;
  const path = `${dir}/${file}.png`;
  await page.screenshot({ path, fullPage });
  return path;
}

/** What the backend's clock says, and whether it is frozen (a dev run only). */
export async function backendClock(request: APIRequestContext): Promise<{ now: string; frozen: boolean }> {
  const answered = await request.get(`${API}/dev/clock`);
  if (!answered.ok()) throw new Error(`GET /dev/clock: ${answered.status()} — is the backend the dev run Playwright starts?`);
  return (await answered.json()) as { now: string; frozen: boolean };
}

/** Stand the backend's frozen clock at this instant (`POST /dev/clock`, a dev run only). */
export async function setBackendClock(request: APIRequestContext, at: string): Promise<void> {
  const moved = await request.post(`${API}/dev/clock`, { data: { at } });
  if (!moved.ok()) throw new Error(`POST /dev/clock: ${moved.status()} ${await moved.text()}`);
}

/** Pa with his own papers, three blood pressures (two from earlier in the week) and five
 *  blood pressure tablets: the feed then has a now card, a reorder card, a reading, the gate,
 *  his story, and a learning card from the allowlisted fixture (checkpoint 8's shape). */
export async function seedFeed(request: APIRequestContext, name = "Pa"): Promise<{ phone: string; token: string; profileId: string }> {
  const phone = freshPhone("+659444");
  const token = await apiToken(request, phone);
  const headers = { Authorization: `Bearer ${token}` };
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    headers,
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: name, language: "en" },
  });
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  // Earlier in the week by the backend's clock, which is frozen for the run.
  const now = Date.parse((await backendClock(request)).now);
  for (const [daysAgo, systolic, diastolic] of [
    [7, 146, 90],
    [3, 142, 88],
  ] as const) {
    const taken_at = new Date(now - daysAgo * 86_400_000).toISOString();
    const added = await request.post(`${API}/profiles/${profileId}/readings`, { headers, data: { systolic, diastolic, taken_at } });
    if (added.status() !== 201) throw new Error(`reading: ${added.status()} ${await added.text()}`);
  }
  await request.post(`${API}/profiles/${profileId}/readings`, { headers, data: { systolic: 138, diastolic: 84 } });
  await seedMedicine(request, token, profileId, { generic: "amlodipine", strength: "5 mg", dose_text: "1 tab OD", quantity: 5 });
  return { phone, token, profileId };
}

/** Record every utterance's speed too: the rate the phone's voice was asked to speak at. */
export async function speechRates(page: Page): Promise<number[]> {
  return page.evaluate(() => (window as unknown as { __rates: number[] }).__rates);
}

/** The warfarin label photo from the paper fixtures, read and confirmed (checkpoint 5): its
 *  safety job finds a recall for a batch that is not his, held for the caregiver. */
export async function seedWarfarinLabel(request: APIRequestContext, token: string, profileId: string): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const bytes = Buffer.concat([PNG, Buffer.from("nura-paper-placeholder:warfarin-label-2024-03-12\n")]);
  const photo = await request.post(`${API}/profiles/${profileId}/photos`, {
    headers,
    data: { data: bytes.toString("base64"), content_type: "image/png", captured_at: "2026-09-14T08:00:00Z" },
  });
  if (photo.status() !== 201) throw new Error(`photo: ${photo.status()} ${await photo.text()}`);
  const card = (await photo.json()) as { card_id: string; fields: { field_id: string; attribute: string }[] };
  const decisions = card.fields.map((field) => ({ field_id: field.field_id, decision: field.attribute === "prescriber" ? "rejected" : "confirmed" }));
  const minted = await request.post(`${API}/profiles/${profileId}/confirmations`, { headers, data: { subject: "review_card", card_id: card.card_id, decisions } });
  if (minted.status() !== 201) throw new Error(`mint: ${minted.status()} ${await minted.text()}`);
  const confirmation_id = ((await minted.json()) as { confirmation_id: string }).confirmation_id;
  const confirmed = await request.post(`${API}/profiles/${profileId}/review-cards/${card.card_id}/confirm`, { headers, data: { decisions, confirmation_id } });
  if (!confirmed.ok()) throw new Error(`confirm: ${confirmed.status()} ${await confirmed.text()}`);
}

/** Move every page the phone kept — Today's and the feed's — past its midnight. */
export async function expireEveryKeptPage(page: Page): Promise<number> {
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
            if (typeof at.key === "string" && (at.key.startsWith("today.") || at.key.startsWith("feed."))) {
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

/** A visit with Dr Tan two days from the frozen Monday, written down on Pa's own yes (E03):
 *  the feed then has a visit card for the week. */
export async function seedVisit(request: APIRequestContext, token: string, profileId: string, at = "2026-09-16T09:00:00+08:00"): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  const provider = await request.post(`${API}/profiles/${profileId}/providers`, { headers, data: { name: "Dr Tan", kind: "doctor" } });
  if (provider.status() !== 201) throw new Error(`provider: ${provider.status()} ${await provider.text()}`);
  const provider_id = ((await provider.json()) as { provider_id: string }).provider_id;
  const purpose = "blood pressure review";
  const yes = await request.post(`${API}/profiles/${profileId}/confirmations`, { headers, data: { subject: "appointment", provider_id, scheduled_at: at, purpose } });
  if (yes.status() !== 201) throw new Error(`yes: ${yes.status()} ${await yes.text()}`);
  const confirmation_id = ((await yes.json()) as { confirmation_id: string }).confirmation_id;
  const visit = await request.post(`${API}/profiles/${profileId}/appointments`, { headers, data: { provider_id, scheduled_at: at, purpose, confirmation_id } });
  if (visit.status() !== 201) throw new Error(`visit: ${visit.status()} ${await visit.text()}`);
}

/** The consult recording the fixtures know (`backend/tests/consult_audio.py`): the four bytes
 *  a webm opens with, a marker and a label. Its digest names what the fixture transcriber and
 *  speaker separator heard (checkpoint 22 sends the same bytes). */
export const CONSULT_BYTES: number[] = [0x1a, 0x45, 0xdf, 0xa3, ...Buffer.from("nura-consult-placeholder:consult-bp-review\n")];

/** What the stand-ins below write down, for the tests to read. */
export interface Stand {
  __recorder: { starts: number; stops: number; types: string[] };
  __clips: string[];
  __locks: { taken: number; released: number };
}

/** A phone that can record: a stand-in `MediaRecorder` that hands back `bytes` as it records —
 *  twenty bytes each timeslice, the way a real one hands over a piece every second, and the
 *  rest when it stops — a microphone, a screen wake lock, and an audio element that writes down
 *  what it was asked to play (Playwright's Chromium has no microphone to give and cannot play
 *  the stand-in). */
export async function fakeRecorder(page: Page, bytes: number[] = CONSULT_BYTES): Promise<void> {
  await page.addInitScript((data: number[]) => {
    const stand = window as unknown as {
      __recorder: { starts: number; stops: number; types: string[] };
      __clips: string[];
      __locks: { taken: number; released: number };
    };
    stand.__recorder = { starts: 0, stops: 0, types: [] };
    stand.__clips = [];
    stand.__locks = { taken: 0, released: 0 };
    class Recorder {
      state = "inactive";
      mimeType: string;
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      private timer: ReturnType<typeof setInterval> | null = null;
      private at = 0;
      static isTypeSupported(type: string): boolean {
        return type === "audio/webm;codecs=opus" || type === "audio/webm";
      }
      constructor(_stream: unknown, options?: { mimeType?: string }) {
        this.mimeType = options?.mimeType ?? "audio/webm";
        stand.__recorder.types.push(this.mimeType);
      }
      start(timeslice?: number): void {
        this.state = "recording";
        stand.__recorder.starts += 1;
        this.at = 0;
        this.timer = setInterval(() => this.hand(20), timeslice ?? 1000);
      }
      private hand(most: number): void {
        const piece = data.slice(this.at, this.at + most);
        this.at += piece.length;
        if (piece.length > 0) this.ondataavailable?.({ data: new Blob([new Uint8Array(piece)], { type: this.mimeType }) });
      }
      stop(): void {
        if (this.state === "inactive") return;
        this.state = "inactive";
        if (this.timer !== null) clearInterval(this.timer);
        stand.__recorder.stops += 1;
        this.hand(data.length);
        this.onstop?.();
      }
    }
    Object.defineProperty(window, "MediaRecorder", { value: Recorder, configurable: true });
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => undefined }] }) },
      configurable: true,
    });
    Object.defineProperty(navigator, "wakeLock", {
      value: {
        request: async () => {
          stand.__locks.taken += 1;
          return { release: async () => void (stand.__locks.released += 1) };
        },
      },
      configurable: true,
    });
    class Audio {
      src = "";
      currentTime = 0;
      private listeners: Record<string, (() => void)[]> = {};
      addEventListener(type: string, listener: () => void): void {
        (this.listeners[type] ??= []).push(listener);
      }
      play(): Promise<void> {
        stand.__clips.push(this.src);
        for (const listener of this.listeners.loadedmetadata ?? []) listener();
        return Promise.resolve();
      }
      pause(): void {}
    }
    Object.defineProperty(window, "Audio", { value: Audio, configurable: true });
  }, bytes);
}

export async function stand(page: Page): Promise<Stand> {
  return page.evaluate(() => {
    const found = window as unknown as Stand;
    return { __recorder: found.__recorder, __clips: found.__clips, __locks: found.__locks };
  });
}

/** `apiToken`, for a person who gives her name when she signs up. */
async function namedToken(request: APIRequestContext, phone: string, name: string): Promise<string> {
  const before = codesSoFar(phone);
  const started = await request.post(`${API}/auth/phone/start`, { data: { phone_e164: phone, display_name: name, language: "en" } });
  if (started.status() !== 202) throw new Error(`start: ${started.status()} ${await started.text()}`);
  const code = await codeFromLog(phone, before);
  const verified = await request.post(`${API}/auth/phone/verify`, { data: { phone_e164: phone, code } });
  if (!verified.ok()) throw new Error(`verify: ${verified.status()} ${await verified.text()}`);
  return ((await verified.json()) as { token: string }).token;
}

const EVERY_PART = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"];

/** Pa, his visit to Dr Tan at half past 10 this morning (the frozen Monday, on his clock, with
 *  its offset — kept as that instant since ADR 0009), Dr Tan's
 *  address, and Mei: his chief, with her note about the place and on the roster this morning.
 *  With `recording`, Pa has already agreed to Nura listening at the visit. */
export async function seedVisitDay(
  request: APIRequestContext,
  { recording = false, at = "2026-09-14T10:30:00+08:00" }: { recording?: boolean; at?: string } = {},
): Promise<{ phone: string; token: string; profileId: string; appointmentId: string; meiId: string; meiPhone: string; meiToken: string }> {
  const phone = freshPhone("+659555");
  const token = await apiToken(request, phone);
  const his = { Authorization: `Bearer ${token}` };
  const words = (await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string };
  const opened = await request.post(`${API}/profiles/mine`, {
    headers: his,
    data: { consent: { wording_version: words.version, language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  if (opened.status() !== 201) throw new Error(`profile: ${opened.status()} ${await opened.text()}`);
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  const tan = await request.post(`${API}/profiles/${profileId}/providers`, {
    headers: his,
    data: { name: "Dr Tan", kind: "doctor", address: "Gleneagles Hospital, 6A Napier Road" },
  });
  if (tan.status() !== 201) throw new Error(`provider: ${tan.status()} ${await tan.text()}`);
  const provider_id = ((await tan.json()) as { provider_id: string }).provider_id;
  const booking = { provider_id, scheduled_at: at, purpose: "blood pressure check" };
  const yes = await request.post(`${API}/profiles/${profileId}/confirmations`, { headers: his, data: { subject: "appointment", ...booking } });
  const confirmation_id = ((await yes.json()) as { confirmation_id: string }).confirmation_id;
  const visit = await request.post(`${API}/profiles/${profileId}/appointments`, { headers: his, data: { ...booking, confirmation_id } });
  if (visit.status() !== 201) throw new Error(`visit: ${visit.status()} ${await visit.text()}`);
  const appointmentId = ((await visit.json()) as { appointment_id: string }).appointment_id;

  // Mei signs up with her own name, as a chief does: the card names her ("Mei's note").
  const meiPhone = freshPhone("+659556");
  const meiToken = await namedToken(request, meiPhone, "Mei");
  const hers = { Authorization: `Bearer ${meiToken}` };
  const meiId = ((await (await request.get(`${API}/me`, { headers: hers })).json()) as { person_id: string }).person_id;
  const letIn = await request.post(`${API}/profiles/${profileId}/consents/sharing`, {
    headers: his,
    data: { holder_phone_e164: meiPhone, holder_display_name: "Mei", scopes: EVERY_PART, role: "chief", window: "always", relationship: "daughter", language: "en", captured_via: "app" },
  });
  if (letIn.status() !== 201) throw new Error(`sharing: ${letIn.status()} ${await letIn.text()}`);
  const key = await request.post(`${API}/profiles/${profileId}/keys`, { headers: his, data: { holder_phone_e164: meiPhone, role: "chief" } });
  if (key.status() !== 201) throw new Error(`key: ${key.status()} ${await key.text()}`);
  const note = await request.post(`${API}/profiles/${profileId}/providers/${provider_id}/notes`, { headers: hers, data: { text: "parking at B2" } });
  if (note.status() !== 201) throw new Error(`note: ${note.status()} ${await note.text()}`);
  const slot = await request.post(`${API}/profiles/${profileId}/roster`, {
    headers: hers,
    data: { person_id: meiId, role: "chief", weekdays: [0], from_time: "09:00:00", to_time: "12:00:00" },
  });
  if (slot.status() !== 201) throw new Error(`roster: ${slot.status()} ${await slot.text()}`);
  if (recording) {
    const recordingWords = (await (await request.get(`${API}/consent/wording?purpose=recording&language=en`)).json()) as { version: string };
    const agreed = await request.post(`${API}/profiles/${profileId}/consents/recording`, {
      headers: his,
      data: { wording_version: recordingWords.version, language: "en", captured_via: "app" },
    });
    if (agreed.status() !== 201) throw new Error(`recording consent: ${agreed.status()} ${await agreed.text()}`);
  }
  return { phone, token, profileId, appointmentId, meiId, meiPhone, meiToken };
}

/** Nothing is ever drawn over a line: the rule #118's feed test checks (`everyLineReadable`,
 *  in feed.spec.ts), with its hit test at the centre of each line, for a screen that scrolls
 *  the page itself (onboarding, the review card). Each visible line under `scope` is scrolled
 *  to the middle of the viewport and must be what the page hits at its centre — never a
 *  button, a field or another tile; each control is hit at its own centre and, when
 *  `minTarget` is given (56 in the patient density), is at least that tall and wide. The
 *  problems found, or an empty list. */
export async function nothingDrawnOverLines(
  scope: Locator,
  options: { lines?: string; controls?: string; minTarget?: number } = {},
): Promise<string[]> {
  const settings = {
    lines: options.lines ?? "h1, h2, p, .label",
    controls: options.controls ?? "button, label.pill, input.field",
    minTarget: options.minTarget ?? 0,
  };
  return scope.evaluate(async (root, { lines, controls, minTarget }) => {
    const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null))));
    const problems: string[] = [];
    const hit = (element: Element) => {
      const box = element.getBoundingClientRect();
      const at = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return at !== null && (at === element || element.contains(at));
    };
    // What is drawn over it, so that a failure names what covers the line.
    const under = (element: Element) => {
      const box = element.getBoundingClientRect();
      const at = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      if (!at) return " (off the screen)";
      const named = at.closest("[class]");
      return ` (under ${at.tagName.toLowerCase()}${named ? `.${String(named.getAttribute("class")).split(" ")[0]}` : ""})`;
    };
    const visible = (element: HTMLElement) => element.offsetParent !== null && element.getBoundingClientRect().height > 0;
    // Brought to the middle of the screen and tested. A miss is tried again: a screen still
    // coming in (a card read after the screen opens) moves a line between the scroll and the
    // test, and only a line still covered after that is a problem.
    const clear = async (element: HTMLElement) => {
      for (let tries = 0; tries < 3; tries++) {
        element.scrollIntoView({ block: "center" });
        await frame();
        if (hit(element)) return true;
      }
      return false;
    };
    for (const line of root.querySelectorAll<HTMLElement>(lines)) {
      if (!visible(line) || !line.textContent?.trim()) continue;
      if (!(await clear(line))) problems.push(`covered: ${line.textContent.trim().slice(0, 70)}${under(line)}`);
    }
    for (const control of root.querySelectorAll<HTMLElement>(controls)) {
      if (!visible(control)) continue;
      const covered = !(await clear(control));
      const name = (control.textContent || control.getAttribute("aria-label") || control.tagName).trim().slice(0, 50);
      if (covered) problems.push(`control covered: ${name}${under(control)}`);
      const box = control.getBoundingClientRect();
      if (minTarget && (box.height < minTarget - 0.5 || box.width < minTarget - 0.5)) {
        problems.push(`smaller than ${minTarget} by ${minTarget}: ${name} (${Math.round(box.width)}×${Math.round(box.height)})`);
      }
    }
    // `clear()` brings each line and control to the centre of the screen in turn, which can
    // leave the shell's own scroll region (D1: the page scrolls in its own region, not the
    // window) sitting wherever the last one needed. Reset both, so a check run straight after
    // this one starts from the top the way this one did.
    window.scrollTo(0, 0);
    document.querySelector<HTMLElement>('[data-testid="shell-scroll"]')?.scrollTo(0, 0);
    return problems;
  }, settings);
}

/** Today has its page, fresh or kept (D1: the proud number that used to say so is on Me now). */
export async function todayReady(page: Page): Promise<void> {
  await expect(page.getByTestId("today-ready")).toBeAttached();
}

/** Open the Me sheet from the header's avatar. By testid, not its accessible name: the Profile
 *  tab is named "Me" too now (plain words), so "Me" alone no longer picks out one button. */
export async function openMe(page: Page): Promise<void> {
  await page.getByTestId("open-me").click();
  await expect(page.getByTestId("me-sheet")).toBeVisible();
}

/** The proud number's card, inside the Me sheet (D1): the backend's summary when it can be
 *  read, and the stand-in counted from Today when it cannot. The sheet must already be open. */
export function proudCard(page: Page): Locator {
  return page.locator("[data-testid=me-proud], [data-testid=proud]").first();
}

/** The proud number, read on the Me sheet (D1): the sheet opened, read, and closed again. */
export async function expectProud(page: Page, value: string): Promise<void> {
  await openMe(page);
  await expect(page.locator("[data-testid=me-proud-number], [data-testid=proud-number]").first()).toHaveText(value);
  await page.getByTestId("sheet-close").click();
  await expect(page.getByTestId("me-sheet")).toHaveCount(0);
}

/** The page's own region scrolled to its end (D1: the page scrolls inside the shell). */
export async function scrollPageToEnd(page: Page): Promise<void> {
  await page.getByTestId("shell-scroll").evaluate((region) => (region.scrollTop = region.scrollHeight));
}

/** Nothing is stuck under the floating tab bar. The bar floats over the page, so a line may pass
 *  under it while the page scrolls — but with the page scrolled as far down as it goes, no line
 *  and no control of the screen may still be under it, or it could never be read or pressed
 *  clear of the bar. `nothingDrawnOverLines` scrolls each line to the middle of the screen and so
 *  never meets the bar at the bottom; this is the check for the bottom. The problems, or []. */
export async function underTheTabBar(scope: Locator, options: { lines?: string; controls?: string } = {}): Promise<string[]> {
  const settings = {
    lines: options.lines ?? "h1, h2, p, .label",
    controls: options.controls ?? "button, label.pill, input.field, a.pill",
  };
  return scope.evaluate(async (root, { lines, controls }) => {
    const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null))));
    const bar = document.querySelector("nav.tabbar");
    if (!bar) return [];
    // To the bottom, and again until the page stops growing there: a screen still reading (the
    // visit's logistics card comes in after the screen opens) grows under a check that
    // scrolled once, and would name lines that the page's own room clears.
    // The shell's page scrolls in its own region (D1); a screen outside the shell, the window.
    const region = document.querySelector<HTMLElement>("[data-testid=shell-scroll]");
    const scroller = region ?? document.scrollingElement ?? document.documentElement;
    let settled = 0;
    for (let tries = 0; tries < 40 && settled < 3; tries++) {
      const height = scroller.scrollHeight;
      scroller.scrollTop = height;
      await frame();
      const atBottom = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1;
      settled = atBottom && scroller.scrollHeight === height ? settled + 1 : 0;
    }
    const top = bar.getBoundingClientRect().top;
    // What the region clips below its own edge is hidden, not under the bar.
    const shown = region ? region.getBoundingClientRect().bottom : window.innerHeight;
    const problems: string[] = [];
    for (const element of root.querySelectorAll<HTMLElement>(`${lines}, ${controls}`)) {
      if (element.offsetParent === null || element.closest("nav.tabbar") || element.closest(".feed-pager")) continue;
      const box = element.getBoundingClientRect();
      if (box.height === 0 || box.top >= Math.min(shown, window.innerHeight)) continue;
      if (Math.min(box.bottom, shown) > top + 0.5) problems.push(`under the tab bar: ${(element.textContent || element.getAttribute("aria-label") || element.tagName).trim().slice(0, 60)}`);
    }
    scroller.scrollTop = 0;
    await frame();
    return problems;
  }, settings);
}

/** What the floating tab bar is drawn over with the page at rest at `scrollY` (the top, by
 *  default): every visible line and control of `main` under the bar. The bar floats over the
 *  page by the design (docs/ui-mockup-v2.html), so at rest it covers whatever is at the bottom
 *  of the screen; this names it. The problems, or []. */
export async function coveredByTheTabBar(page: Page, scrollY = 0): Promise<string[]> {
  return page.evaluate(async (at) => {
    const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(null))));
    const bar = document.querySelector("nav.tabbar");
    if (!bar) return [];
    const region = document.querySelector<HTMLElement>("[data-testid=shell-scroll]");
    const scroller = region ?? document.scrollingElement ?? document.documentElement;
    scroller.scrollTop = at;
    await frame();
    const top = bar.getBoundingClientRect().top;
    // What the shell's region clips below its own edge is hidden, not covered by the bar.
    const shown = region ? region.getBoundingClientRect().bottom : window.innerHeight;
    const covered: string[] = [];
    for (const element of document.querySelectorAll<HTMLElement>("main h1, main h2, main p, main .label, main button, main a.pill, main label.pill")) {
      if (element.closest("nav.tabbar") || element.closest(".feed-pager") || element.offsetParent === null) continue;
      const box = element.getBoundingClientRect();
      if (box.height > 0 && Math.min(box.bottom, shown) > top + 0.5 && box.top < Math.min(shown, window.innerHeight)) {
        covered.push(`${element.tagName.toLowerCase()}: ${(element.textContent || element.getAttribute("aria-label") || "").trim().slice(0, 50)}`);
      }
    }
    scroller.scrollTop = 0;
    await frame();
    return covered;
  }, scrollY);
}
