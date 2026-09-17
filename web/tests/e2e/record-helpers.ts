import { randomInt } from "node:crypto";
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { API, backendClock, codeFromLog, codesSoFar, nothingDrawnOverLines, signInThroughTheApp, openMe } from "./helpers";

/** What the Record's walks (W5) seed over the API, and the two checks every screen gets:
 *  the density it is walked in, and nothing drawn over a line (56px targets in his). */

export type Look = "patient" | "caregiver";
export const LOOKS: readonly Look[] = ["patient", "caregiver"];

export const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

export const EVERY_PART = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"];

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** A paper the fixture extractor knows, by the bytes it knows it by (backend/tests/fixtures/paper/). */
export function placeholderPng(label: string): Buffer {
  return Buffer.concat([PNG, Buffer.from(`nura-paper-placeholder:${label}\n`)]);
}

/** A photo the extractor does not know: a card with nothing read, for him to type the label. */
export function unknownPng(): Buffer {
  return Buffer.concat([PNG, Buffer.from(`a label photo the extractor does not know ${Math.random()}\n`)]);
}

/** A Singapore-shaped number nobody on this dev database has yet: `+658` and seven random
 *  digits. The dev database keeps every account from every run, so four random digits (the
 *  shared helper's) come round again within a few runs; seven do not, and `+658` keeps clear
 *  of every `+659…` prefix the other specs use. */
export function uniquePhone(): string {
  return `+658${String(randomInt(0, 10_000_000)).padStart(7, "0")}`;
}

export interface Person {
  phone: string;
  token: string;
  personId: string;
}

export interface Papers extends Person {
  profileId: string;
}

/** A person signed up by phone code over the API, with the name she gives. */
export async function signUp(request: APIRequestContext, phone: string, name: string): Promise<Person> {
  const before = codesSoFar(phone);
  const started = await request.post(`${API}/auth/phone/start`, { data: { phone_e164: phone, display_name: name, language: "en" } });
  expect(started.status(), await started.text()).toBe(202);
  const code = await codeFromLog(phone, before);
  const verified = await request.post(`${API}/auth/phone/verify`, { data: { phone_e164: phone, code } });
  expect(verified.ok(), await verified.text()).toBe(true);
  const session = (await verified.json()) as { token: string; person_id: string };
  return { phone, token: session.token, personId: session.person_id };
}

export async function holdWording(request: APIRequestContext): Promise<string> {
  return ((await (await request.get(`${API}/consent/wording?language=en`)).json()) as { version: string }).version;
}

/** Pa, with his own papers, in English. */
export async function openOwn(request: APIRequestContext, name = "Pa"): Promise<Papers> {
  const person = await signUp(request, uniquePhone(), name);
  const opened = await request.post(`${API}/profiles/mine`, {
    ...auth(person.token),
    data: { consent: { wording_version: await holdWording(request), language: "en", captured_via: "app" }, display_name: name, language: "en" },
  });
  expect(opened.status(), await opened.text()).toBe(201);
  return { ...person, profileId: ((await opened.json()) as { profile_id: string }).profile_id };
}

/** He lets someone in to these parts, on his own yes, and cuts her a key with this role. */
export async function letIn(request: APIRequestContext, pa: Pick<Papers, "token" | "profileId">, name: string, role: string, scopes: string[]): Promise<Person> {
  const person = await signUp(request, uniquePhone(), name);
  const agreed = await request.post(`${API}/profiles/${pa.profileId}/consents/sharing`, {
    ...auth(pa.token),
    data: { holder_phone_e164: person.phone, holder_display_name: name, scopes, role, window: "always", relationship: null, language: "en", captured_via: "app" },
  });
  expect(agreed.status(), await agreed.text()).toBe(201);
  const key = await request.post(`${API}/profiles/${pa.profileId}/keys`, { ...auth(pa.token), data: { holder_phone_e164: person.phone, role, scopes } });
  expect(key.status(), await key.text()).toBe(201);
  return person;
}

export async function yes(request: APIRequestContext, token: string, profileId: string, body: Record<string, unknown>): Promise<string> {
  const minted = await request.post(`${API}/profiles/${profileId}/confirmations`, { ...auth(token), data: body });
  expect(minted.status(), await minted.text()).toBe(201);
  return ((await minted.json()) as { confirmation_id: string }).confirmation_id;
}

/** A photo of a paper, read into a review card, and every line said yes to (one yes). */
export async function confirmPhoto(request: APIRequestContext, token: string, profileId: string, bytes: Buffer): Promise<{ cardId: string; artifactId: string }> {
  const photo = await request.post(`${API}/profiles/${profileId}/photos`, {
    ...auth(token),
    data: { data: bytes.toString("base64"), content_type: "image/png", captured_at: "2026-09-14T01:00:00Z" },
  });
  expect(photo.status(), await photo.text()).toBe(201);
  const card = (await photo.json()) as { card_id: string; artifact_id: string; fields: { field_id: string; unreadable: boolean }[] };
  const decisions = card.fields.map((field) => ({ field_id: field.field_id, decision: field.unreadable ? "rejected" : "confirmed" }));
  const confirmation_id = await yes(request, token, profileId, { subject: "review_card", card_id: card.card_id, decisions });
  const done = await request.post(`${API}/profiles/${profileId}/review-cards/${card.card_id}/confirm`, { ...auth(token), data: { decisions, confirmation_id } });
  expect(done.ok(), await done.text()).toBe(true);
  return { cardId: card.card_id, artifactId: card.artifact_id };
}

export async function addProvider(request: APIRequestContext, pa: Papers, name = "Dr Tan", address?: string): Promise<string> {
  const made = await request.post(`${API}/profiles/${pa.profileId}/providers`, { ...auth(pa.token), data: { name, kind: "doctor", ...(address ? { address } : {}) } });
  expect(made.status(), await made.text()).toBe(201);
  return ((await made.json()) as { provider_id: string }).provider_id;
}

export async function openIllness(request: APIRequestContext, pa: Papers, label: string): Promise<string> {
  const made = await request.post(`${API}/profiles/${pa.profileId}/episodes`, { ...auth(pa.token), data: { kind: "illness", label } });
  expect(made.status(), await made.text()).toBe(201);
  return ((await made.json()) as { episode_id: string }).episode_id;
}

/** A visit written down on his yes, then each step of its status on its own yes. */
export async function book(
  request: APIRequestContext,
  pa: Papers,
  providerId: string,
  at: string,
  purpose: string,
  steps: string[] = [],
  episodeId?: string,
): Promise<string> {
  const confirmation_id = await yes(request, pa.token, pa.profileId, { subject: "appointment", provider_id: providerId, scheduled_at: at, purpose });
  const visit = await request.post(`${API}/profiles/${pa.profileId}/appointments`, {
    ...auth(pa.token),
    data: { provider_id: providerId, scheduled_at: at, purpose, confirmation_id, ...(episodeId ? { episode_id: episodeId } : {}) },
  });
  expect(visit.status(), await visit.text()).toBe(201);
  const appointmentId = ((await visit.json()) as { appointment_id: string }).appointment_id;
  for (const status of steps) {
    const step = await yes(request, pa.token, pa.profileId, { subject: "appointment_status", appointment_id: appointmentId, status });
    const moved = await request.post(`${API}/profiles/${pa.profileId}/appointments/${appointmentId}/status`, { ...auth(pa.token), data: { status, confirmation_id: step } });
    expect(moved.ok(), await moved.text()).toBe(true);
  }
  return appointmentId;
}

/** An instant this many days from the backend's frozen now. */
export async function daysFromNow(request: APIRequestContext, days: number): Promise<string> {
  const now = Date.parse((await backendClock(request)).now);
  return new Date(now + days * 86_400_000).toISOString();
}

/** Sign in through the app, through the door to someone else's papers when the app shows
 *  one (a person with one key and no papers of her own is taken straight to them). */
export async function signInAs(page: Page, person: Pick<Person, "phone">, name: string, door = false): Promise<void> {
  await signInThroughTheApp(page, person.phone, name);
  const bar = page.locator("nav.tabbar");
  if (door) {
    const key = page.getByTestId("door-key");
    await expect(key.or(bar)).toBeVisible();
    if (await key.isVisible()) await key.click();
  }
  await expect(bar).toBeVisible();
}

/** The Record's first screen from the tab bar: the Health tab opens the Health screen
 *  (docs/design/nura-concept-board.html), and its own row opens the Record — his papers, his
 *  blood tests and the rest of it, one tap further on. */
export async function openRecord(page: Page): Promise<void> {
  await page.getByTestId("tab-health").click();
  await page.getByTestId("health-record-hub").click();
  await expect(page.getByTestId("record-hub")).toBeVisible();
}

/** The density chosen on the Me sheet (D1), then the Record's first screen. */
export async function lookAs(page: Page, look: Look): Promise<void> {
  await openMe(page);
  await page.getByTestId(`density-${look}`).click();
  await expect(page.locator("html")).toHaveAttribute("data-density", look);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("me-sheet")).toHaveCount(0);
  await openRecord(page);
}

/** #118's hit test on the screen as it is: every line readable, every control reachable, and
 *  56px targets in his density. */
export async function readable(page: Page, look: Look): Promise<void> {
  // A Record screen says it is busy while its reads are in flight; check it once it is not.
  await page.waitForFunction(() => document.querySelector("main")?.getAttribute("aria-busy") !== "true");
  expect(await nothingDrawnOverLines(page.locator("main"), { minTarget: look === "patient" ? 56 : 0 })).toEqual([]);
}
