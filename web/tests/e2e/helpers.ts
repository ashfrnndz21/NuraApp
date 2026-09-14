import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { APIRequestContext, Page } from "@playwright/test";

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
    const synth = {
      cancel: () => undefined,
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
