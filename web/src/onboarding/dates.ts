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
