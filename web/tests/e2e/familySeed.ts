import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { APIRequestContext, Locator, Page } from "@playwright/test";
import { FROZEN_CLOCK } from "../../playwright.config";
import { API, codeFromLog, codesSoFar, freshPhone, nothingDrawnOverLines, setBackendClock } from "./helpers";

/** The household checkpoint 26 walks, seeded over the API the way checkpoint 13 seeds it:
 *  Pa owns his papers (English, WhatsApp agreed, a private note of his own); Mei is his chief
 *  and on duty all Monday; Kit, his son, holds a caregiver key that reads the family thread;
 *  Siti, the helper, has Pa's agreement but no key until someone cuts her one. */

export interface Person {
  phone: string;
  token: string;
  personId: string;
  name: string;
}

export interface Family {
  pa: Person;
  mei: Person;
  kit: Person;
  siti: Person;
  profileId: string;
}

const HERE = dirname(fileURLToPath(import.meta.url));
export const ICS = readFileSync(resolve(HERE, "../../../backend/tests/fixtures/calendar/three-events.ics"));

const EVERY_PART = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"];
const KITS = ["medicines", "visits", "readings", "records", "emergency", "family"];
const SITIS = ["medicines", "emergency", "send"];

export const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

async function ok(what: string, answer: { ok(): boolean; status(): number; text(): Promise<string> }): Promise<void> {
  if (!answer.ok()) throw new Error(`${what}: ${answer.status()} ${await answer.text()}`);
}

export async function person(request: APIRequestContext, prefix: string, name: string, language = "en"): Promise<Person> {
  const phone = freshPhone(prefix);
  const before = codesSoFar(phone);
  await ok("start", await request.post(`${API}/auth/phone/start`, { data: { phone_e164: phone, display_name: name, language } }));
  const code = await codeFromLog(phone, before);
  const verified = await request.post(`${API}/auth/phone/verify`, { data: { phone_e164: phone, code } });
  await ok("verify", verified);
  const token = ((await verified.json()) as { token: string }).token;
  const me = (await (await request.get(`${API}/me`, { headers: auth(token) })).json()) as { person_id: string };
  return { phone, token, personId: me.person_id, name };
}

async function wording(request: APIRequestContext, purpose: string, language = "en"): Promise<string> {
  return ((await (await request.get(`${API}/consent/wording?purpose=${purpose}&language=${language}`)).json()) as { version: string }).version;
}

export async function letIn(request: APIRequestContext, family: Family, who: Person, scopes: string[], relationship: string): Promise<void> {
  await ok(
    `sharing with ${who.name}`,
    await request.post(`${API}/profiles/${family.profileId}/consents/sharing`, {
      headers: auth(family.pa.token),
      data: { holder_phone_e164: who.phone, holder_display_name: who.name, scopes, relationship, language: "en", captured_via: "app" },
    }),
  );
}

export async function cutKey(request: APIRequestContext, family: Family, who: Person, role: string, scopes?: string[]): Promise<void> {
  await ok(
    `${role} key for ${who.name}`,
    await request.post(`${API}/profiles/${family.profileId}/keys`, { headers: auth(family.pa.token), data: { holder_phone_e164: who.phone, role, ...(scopes ? { scopes } : {}) } }),
  );
}

export async function seedFamily(request: APIRequestContext, { sitiKey = false }: { sitiKey?: boolean } = {}): Promise<Family> {
  const pa = await person(request, "+659661", "Pa");
  const opened = await request.post(`${API}/profiles/mine`, {
    headers: auth(pa.token),
    data: { consent: { wording_version: await wording(request, "hold_health_record"), language: "en", captured_via: "app" }, display_name: "Pa", language: "en" },
  });
  await ok("profile", opened);
  const profileId = ((await opened.json()) as { profile_id: string }).profile_id;
  const family: Family = {
    pa,
    mei: await person(request, "+659662", "Mei"),
    kit: await person(request, "+659663", "Kit"),
    siti: await person(request, "+659664", "Siti"),
    profileId,
  };
  const his = auth(pa.token);
  await ok(
    "whatsapp",
    await request.post(`${API}/profiles/${profileId}/consents/whatsapp`, { headers: his, data: { wording_version: await wording(request, "whatsapp"), language: "en", captured_via: "app" } }),
  );
  await letIn(request, family, family.mei, EVERY_PART, "daughter");
  await letIn(request, family, family.kit, KITS, "son");
  await letIn(request, family, family.siti, SITIS, "helper");
  await cutKey(request, family, family.mei, "chief");
  await cutKey(request, family, family.kit, "caregiver", KITS);
  if (sitiKey) await cutKey(request, family, family.siti, "helper");
  await ok("note", await request.post(`${API}/profiles/${profileId}/notes`, { headers: his, data: { text: "I worry about the stairs." } }));
  await ok(
    "roster",
    await request.post(`${API}/profiles/${profileId}/roster`, {
      headers: his,
      data: { person_id: family.mei.personId, role: "chief", weekdays: [0], from_time: "00:00:00", to_time: "23:59:00" },
    }),
  );
  return family;
}

/** Pa agrees to the calendar, and Mei hands Nura the three-event file: two visits proposed,
 *  the lunch kept nowhere (checkpoint 17's file). */
export async function seedProposals(request: APIRequestContext, family: Family): Promise<void> {
  const connected = await request.post(`${API}/profiles/${family.profileId}/connectors/calendar`, {
    headers: auth(family.pa.token),
    data: { consent: { wording_version: await wording(request, "calendar"), language: "en", captured_via: "app" } },
  });
  await ok("calendar", connected);
  const connectorId = ((await connected.json()) as { connector_id: string }).connector_id;
  await ok(
    "scan",
    await request.post(`${API}/profiles/${family.profileId}/connectors/${connectorId}/scan`, { headers: auth(family.mei.token), data: { ics: ICS.toString("base64") } }),
  );
}

/** Run the delivery engine at a moment on his wall clock, then stand the clock back where
 *  every other test expects it. */
export async function runTriggersAt(request: APIRequestContext, family: Family, at: string): Promise<void> {
  await setBackendClock(request, at);
  try {
    await ok("run-triggers", await request.post(`${API}/dev/run-triggers`, { data: { profile_id: family.profileId } }));
  } finally {
    await setBackendClock(request, FROZEN_CLOCK);
  }
}

/** The patient density's rule: nothing drawn over a line, every control 56 by 56. */
export const patientScreenOk = (page: Page) =>
  nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label, blockquote, td, th", controls: "button, label.pill, input.field, a.pill", minTarget: 56 });

/** The caregiver density at 360 wide: nothing drawn over a line, and nothing sideways. */
export async function caregiverScreenOk(page: Page): Promise<string[]> {
  const problems = await nothingDrawnOverLines(page.locator("main"), { lines: "h1, h2, p, .label, blockquote, td, th", controls: "button, label.pill, input.field, a.pill" });
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (wide > 0) problems.push(`scrolls sideways by ${wide}px`);
  return problems;
}

/** Family: the chief's tab; on his phone, the Me sheet's "Family" (D1). */
export async function openFamily(page: Page): Promise<void> {
  if ((await page.getByTestId("tab-connect").count()) > 0) return page.getByTestId("tab-connect").click();
  await page.getByRole("button", { name: "Me", exact: true }).click();
  await page.getByTestId("me-family").click();
}

export async function openFamilyPart(page: Page, part: string): Promise<Locator> {
  await openFamily(page);
  await page.getByTestId(`open-${part}`).click();
  const main = page.getByTestId(`family-${part}`);
  await main.waitFor();
  return main;
}
