/**
 * Dates the way he says them (plain-words rule 5: the day and the date,
 * never "the 7th", never a number format) — ported from
 * `web/src/onboarding/dates.ts` so the mobile client says the same
 * thing the web one does, not a re-invented version of the rule.
 *
 * A backend date ("2026-09-05") is a calendar day, so it is read as
 * local midnight, not UTC — parsing it with `new Date("2026-09-05")`
 * directly would read it as UTC midnight and can print the day before
 * in a timezone west of UTC.
 */
function localDay(iso: string): Date {
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
}

/**
 * "Friday 5 September": the weekday and the date, no comma and no year
 * — rule 5's own example, exactly (`web/src/onboarding/dates.ts`'s
 * `saidDate`, this module's own twin). `Intl`'s "long" weekday format
 * inserts a comma by default, so the two parts are formatted
 * separately and joined without one.
 */
export function saidDate(iso: string, locale = 'en-SG'): string {
  const day = localDay(iso);
  const weekday = day.toLocaleDateString(locale, { weekday: 'long' });
  const monthDay = day.toLocaleDateString(locale, { day: 'numeric', month: 'long' });
  return locale.startsWith('zh') ? `${monthDay}${weekday}` : `${weekday} ${monthDay}`;
}

/** "Friday, 5 September 2026": a paper's own date carries its year (web's `paperDate` twin). */
export function paperDate(iso: string, locale = 'en-SG'): string {
  return localDay(iso).toLocaleDateString(locale, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/** An ISO date, matched loosely so a value carrying a clock time ("2025-01-21T21:16") is caught too. */
const ISO_DATE_VALUE = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/;

function timeLine(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit', hour12: locale.startsWith('en') }).format(date);
}

/**
 * A report row's own printed *value*, read as a date (and, when the
 * paper carries one, a time) in his own words: "21 January 2025, 9:16
 * pm" — never the ISO string the backend sends. Ported from
 * `web/src/onboarding/dates.ts`'s `fieldValueDate`. `null` for anything
 * that is not a valid ISO date — left exactly as printed, the caller's
 * job, never guessed at here.
 */
export function fieldValueDate(value: string, locale = 'en-SG'): string | null {
  const match = ISO_DATE_VALUE.exec(value.trim());
  if (!match) return null;
  const [, y, mo, d, hour, minute] = match;
  const year = Number(y);
  const month = Number(mo) - 1;
  const day = Number(d);
  const date = new Date(year, month, day, hour != null ? Number(hour) : 0, minute != null ? Number(minute) : 0);
  if (date.getFullYear() !== year || date.getMonth() !== month || date.getDate() !== day) return null;
  const dateText = date.toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric' });
  if (hour == null) return dateText;
  return `${dateText}, ${timeLine(date, locale)}`;
}

/** The value a report row shows: a date value worded, everything else exactly as read. */
export function displayFieldValue(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'string') {
    const asDate = fieldValueDate(value);
    if (asDate) return asDate;
    return value;
  }
  return String(value);
}
