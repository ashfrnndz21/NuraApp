import type { ConsentOut } from "../api/types";
import type { DigestOut, GrantOut, KeyRole, KeyWindow, NudgeMetricsOut, PrivacyOut, ProposalOut, RosterSlotOut, Scope } from "../api/familyTypes";

/** The Family screens' arithmetic, pure: no sentence is made here. Every line a person reads
 *  about his record is the backend's; this only sorts, picks and formats data. */

/** Every part a key can open, in the order the backend's words list them (`SCOPE_WORDS`). */
export const PARTS: readonly Scope[] = ["medicines", "visits", "readings", "records", "notes", "money", "emergency", "family", "ask", "send"];

/** The parts he may keep to himself: all but the emergency card (`ONLY_ME_SCOPES`). */
export const ONLY_ME_PARTS: readonly Scope[] = PARTS.filter((part) => part !== "emergency");

export const ROLES: readonly KeyRole[] = ["chief", "caregiver", "viewer", "helper", "emergency", "clinic"];

/** From the longest to the shortest: narrowing moves right. */
export const WINDOWS: readonly KeyWindow[] = ["always", "thirty_days", "seventy_two_hours", "one_day"];

/** The message templates the backend keeps (`app.family.strings.PUSH_TEMPLATES`), with the
 *  slots each needs (`TEMPLATE_SLOTS`). The words are the backend's, seen only in the preview. */
export const TEMPLATES: readonly { id: string; slots: readonly ("who" | "when" | "doctor" | "day")[] }[] = [
  { id: "pickup", slots: ["who", "when"] },
  { id: "call_you", slots: ["who", "when"] },
  { id: "see_doctor", slots: ["who", "doctor", "day"] },
  { id: "thinking_of_you", slots: ["who"] },
  { id: "weigh_tomorrow", slots: ["who"] },
  { id: "drink_water", slots: [] },
  { id: "water_pill_morning", slots: [] },
];

/** Singapore and Malaysia both keep UTC+8 all year: his wall clock. */
export const WALL_OFFSET_MS = 8 * 3_600_000;
export const WALL_OFFSET = "+08:00";

/** The part names a key holds, less `profile`, which every key holds. */
export function partsOf(scopes: readonly string[]): Scope[] {
  return PARTS.filter((part) => scopes.includes(part));
}

/** Who each person on the family list is, by the backend's own name for them. */
export function namesOf(grants: readonly GrantOut[]): Map<string, string> {
  return new Map(grants.map((grant) => [grant.holder_person_id, grant.holder_name]));
}

/** Midnight at the start of his day, as an instant: where "today's" digest starts. */
export function startOfHisDay(nowMs: number, daysBack = 0): string {
  const wall = new Date(nowMs + WALL_OFFSET_MS);
  const midnight = Date.UTC(wall.getUTCFullYear(), wall.getUTCMonth(), wall.getUTCDate() - daysBack) - WALL_OFFSET_MS;
  return new Date(midnight).toISOString();
}

/** A moment as a `datetime-local` value on his wall clock ("2026-09-14T11:00"). */
export function toWallInput(ms: number): string {
  return new Date(ms + WALL_OFFSET_MS).toISOString().slice(0, 16);
}

/** A `datetime-local` value on his wall clock as an instant with its offset, the way the
 *  backend takes an aware time. Null when the value is not a time. */
export function fromWallInput(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  return `${value}:00${WALL_OFFSET}`;
}

/** A message's first moment and its last, by default: the next quarter hour after an hour
 *  from now, and twelve hours after that. */
export function pushWindow(nowMs: number): { sendAt: string; expiresAt: string } {
  const quarter = 15 * 60_000;
  const send = Math.ceil((nowMs + 3_600_000) / quarter) * quarter;
  return { sendAt: toWallInput(send), expiresAt: toWallInput(send + 12 * 3_600_000) };
}

/** A moment as his wall clock shows it, in the reader's language: data, not a sentence. */
export function wallTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone: "Asia/Singapore",
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** Monday to Sunday, short, in the reader's language (the roster's 0 is Monday). */
export function weekdayNames(locale: string): string[] {
  const monday = Date.UTC(2026, 8, 14, 4); // Monday 14 September 2026, midday on his wall
  const format = new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "Asia/Singapore" });
  return Array.from({ length: 7 }, (_, day) => format.format(new Date(monday + day * 86_400_000)));
}

/** "07:00" from the backend's "07:00:00". */
export function hhmm(time: string): string {
  return time.slice(0, 5);
}

export interface SlotRow {
  slotId: string;
  who: string;
  days: string;
  from: string;
  to: string;
}

/** One roster slot as a row of data: who, which days, from, to. */
export function slotRow(slot: RosterSlotOut, names: Map<string, string>, locale: string): SlotRow {
  const days = slot.weekdays
    ? slot.weekdays
        .slice()
        .sort((a, b) => a - b)
        .map((day) => weekdayNames(locale)[day])
        .join(" ")
    : [slot.starts_on, slot.ends_on].filter(Boolean).join(" – ");
  return { slotId: slot.slot_id, who: names.get(slot.person_id) ?? "", days, from: hhmm(slot.from_time), to: hhmm(slot.to_time) };
}

/** The digest in the order the backend wrote it: the headline, each entry's lines with the
 *  family member's own words under them, then the closing lines (who is on duty, a quiet day). */
export function digestView(digest: DigestOut): { headline: string; entries: { lines: string[]; text: string | null }[]; closing: string[] } {
  const said = digest.entries.reduce((count, entry) => count + entry.lines.length, 0);
  return {
    headline: digest.headline,
    entries: digest.entries.map((entry) => ({ lines: entry.lines, text: entry.text })),
    closing: digest.lines.slice(1 + said),
  };
}

/** The agreements still in force, oldest first, as the backend listed them. */
export function inForce(consents: readonly ConsentOut[]): ConsentOut[] {
  return consents.filter((consent) => !consent.revoked_at);
}

/** An agreement's own words, one line each, as he read them. */
export function wordingLines(consent: ConsentOut): string[] {
  return consent.wording_text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** The parts marked "only me" right now. */
export function markedParts(rows: readonly PrivacyOut[]): Set<Scope> {
  return new Set(rows.filter((row) => row.lifted_at === null).map((row) => row.scope));
}

/** The proposals still waiting for a yes or a no, soonest first. */
export function waiting(found: readonly ProposalOut[]): ProposalOut[] {
  return found.filter((proposal) => proposal.status === "proposed").sort((a, b) => a.starts_at.localeCompare(b.starts_at));
}

export interface WeekRow {
  week: string;
  startsOn: string;
  taps: number;
  fineToday: number;
  /** The share as a whole percentage, or null when there were no taps to share. */
  finePercent: number | null;
  kinds: { kind: string; handedOver: number; accepted: number; dismissed: number }[];
}

/** The metrics as rows of counts, newest week first. Counts only: there is nothing else. */
export function weekRows(metrics: NudgeMetricsOut): WeekRow[] {
  return metrics.weeks
    .map((week) => ({
      week: week.week,
      startsOn: week.starts_on,
      taps: week.taps,
      fineToday: week.fine_today,
      finePercent: week.fine_share === null ? null : Math.round(week.fine_share * 100),
      kinds: Object.entries(week.nudges)
        .map(([kind, counts]) => ({ kind, handedOver: counts.handed_over, accepted: counts.accepted, dismissed: counts.dismissed }))
        .sort((a, b) => a.kind.localeCompare(b.kind)),
    }))
    .sort((a, b) => b.startsOn.localeCompare(a.startsOn));
}

/** A file's bytes as base64, the way the scan takes an .ics. */
export function base64OfBytes(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  for (let at = 0; at < view.length; at += 0x8000) binary += String.fromCharCode(...view.subarray(at, at + 0x8000));
  return btoa(binary);
}
