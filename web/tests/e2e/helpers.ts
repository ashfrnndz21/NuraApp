import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { APIRequestContext, Locator, Page } from "@playwright/test";

/** The same three things `backend/scripts/checkpoint.py` does: a fresh number every run, the
 *  login code read from the `make dev` log (never from the API), and a medicine seeded by
 *  the label → OK → write flow so Today has a Now card. */

export const API = process.env.NURA_BASE_URL ?? "http://127.0.0.1:8000";
const HERE = dirname(fileURLToPath(import.meta.url));
const DEV_LOG = process.env.NURA_DEV_LOG ?? resolve(HERE, "../../../backend/.dev.log");
const CODE_LINE = /login code for (\+[0-9]+): ([0-9]{6})/g;

export function freshPhone(prefix = "+659777"): string {
  return `${prefix}${String(Math.floor(Math.random() * 10000)).padStart(4, "0")}`;
}

/** The newest code the server logged for this number, waiting up to five seconds for it. */
export async function codeFromLog(phone: string, after: number): Promise<string> {
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
  if (!existsSync(DEV_LOG)) return 0;
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
export async function signInThroughTheApp(page: Page, phone: string, name: string): Promise<void> {
  await page.goto("./");
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
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    (window as unknown as { __cancels: number }).__cancels = 0;
    const synth = {
      // Every stop is counted, so a test can see a voice stop when its card leaves the screen.
      cancel: () => {
        (window as unknown as { __cancels: number }).__cancels += 1;
      },
      speak: (u: { text: string }) => spoken.push(u.text),
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

/** The phone's copy of anyone's papers in IndexedDB: every stored value that names a medicine. */
export async function medicinesInIndexedDb(page: Page): Promise<string[]> {
  return page.evaluate(
    () =>
      new Promise<string[]>((resolve) => {
        const opened = indexedDB.open("nura", 1);
        opened.onsuccess = () => {
          const all = opened.result.transaction("kv", "readonly").objectStore("kv").getAll();
          all.onsuccess = () =>
            resolve(all.result.map((value: unknown) => JSON.stringify(value)).filter((value: string) => /amlodipine|blood pressure/.test(value)));
        };
        opened.onerror = () => resolve(["error"]);
      }),
  );
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
    const visible = (element: HTMLElement) => element.offsetParent !== null && element.getBoundingClientRect().height > 0;
    for (const line of root.querySelectorAll<HTMLElement>(lines)) {
      if (!visible(line) || !line.textContent?.trim()) continue;
      line.scrollIntoView({ block: "center" });
      await frame();
      if (!hit(line)) problems.push(`covered: ${line.textContent.trim().slice(0, 70)}`);
    }
    for (const control of root.querySelectorAll<HTMLElement>(controls)) {
      if (!visible(control)) continue;
      control.scrollIntoView({ block: "center" });
      await frame();
      const name = (control.textContent || control.getAttribute("aria-label") || control.tagName).trim().slice(0, 50);
      if (!hit(control)) problems.push(`control covered: ${name}`);
      const box = control.getBoundingClientRect();
      if (minTarget && (box.height < minTarget - 0.5 || box.width < minTarget - 0.5)) {
        problems.push(`smaller than ${minTarget} by ${minTarget}: ${name} (${Math.round(box.width)}×${Math.round(box.height)})`);
      }
    }
    window.scrollTo(0, 0);
    return problems;
  }, settings);
}
