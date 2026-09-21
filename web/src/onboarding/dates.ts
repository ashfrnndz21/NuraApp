/** Dates the way he says them (docs/plain-words.md rule 5): the day and the date, never
 *  "the 7th", never a number format. A backend date ("2023-09-07") is a calendar day, so it
 *  is read as local midnight, not UTC. */

function localDay(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return new Date(year!, (month ?? 1) - 1, day ?? 1);
}

/** "Thursday, 7 September 2023": a paper's date carries its year. */
export function paperDate(iso: string, locale: string): string {
  return localDay(iso).toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

/** "Tuesday, 15 September": a day in the coming week. */
export function dayLine(iso: string, locale: string): string {
  return localDay(iso).toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long" });
}

/** An ISO date, matched loosely so a value the paper prints with a clock time on it
 *  ("2025-01-21T21:16") is caught too, not only a bare day. Group 4/5 hold the hour and
 *  minute when the value carries a time at all. */
const ISO_DATE_VALUE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

/** A report row's own printed value, read as a date (and, when the paper carries one, a
 *  time) in his own language: "21 January 2025, 9:16 pm" — never the ISO string the backend
 *  sends (E02-07 library part A #3, the owner's own screenshot: "Collected On
 *  2025-01-21T21:16"). Local midnight for a bare date, the paper's own printed clock time
 *  when the value carries one. `null` for anything that is not a valid ISO date — that
 *  value is left exactly as printed, the caller's job, never guessed at here. */
export function fieldValueDate(value: string, locale: string): string | null {
  const match = ISO_DATE_VALUE.exec(value.trim());
  if (!match) return null;
  const [, y, mo, d, hour, minute] = match;
  const year = Number(y);
  const month = Number(mo) - 1;
  const day = Number(d);
  const date = new Date(year, month, day, hour != null ? Number(hour) : 0, minute != null ? Number(minute) : 0);
  // A calendar day that does not exist ("2025-02-30") rolls over in `Date`; caught here so
  // it is left as printed rather than shown as the day it rolled over to.
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null;
  const dateText = date.toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" });
  if (hour == null) return dateText;
  return `${dateText}, ${timeLine(date, locale)}`;
}

/** "9:16 pm" in English, "21:16" in Malay and Chinese — the same clock format every time in
 *  the app uses (`web/src/today/model.ts`), duplicated in miniature here to keep this module
 *  free of a dependency on `today/` for one line. */
function timeLine(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit", hour12: locale.startsWith("en") }).format(date);
}
