import type { FactOut, FoodCatalogItemOut, FoodEntryOut, Meal, MetricRowOut, RingOut } from "../api/types";
import { fill, type Strings } from "../strings";
import { dayKey } from "../today/model";

/** The Health tab (docs/design/nura-concept-board.html, the Health screen): "This week"'s
 *  ring and metric rows come straight from the backend's own words (`health_tab.py`,
 *  `health_strings.py`) — nothing here re-says them. What is worked out on the phone is small:
 *  whose health it is, whether a key's scope shows the readings at all, and which of his meals
 *  today have something to show. */

/** Whose health this is, in his own words or hers about him by name — the same rule as every
 *  other tab (`places.visitsOwn`/`visitsOther`). */
export function healthTitle(owner: boolean, name: string, s: Strings): string {
  return owner ? s.health.title : fill(s.health.titleOther, { name });
}

/** A key without the readings scope does not open his blood pressure and sugar — the block is
 *  shown withheld, named, never left off the screen in silence. */
export function readingsWithheld(scopes: readonly string[]): boolean {
  return !scopes.includes("readings");
}

/** The week ring (`ThisWeek`, package 10): a fresh profile with no active medicines has
 *  nothing for "doses taken this week" to count — `total` is `0` — and the backend's own words
 *  for that count are literally "0 of 0" (`ring_words`, `app.channels.health_strings`), which
 *  read as a broken score, not a calm nothing-yet. `total` of `null` (`check_ins`, a ring kind
 *  this screen does not use today) counts as nothing to show either, the same caution
 *  `ProgressRing`'s own "required, never optional" `source` rule already keeps. Pure so the
 *  ring's empty-state branch is a unit, not only ever seen through a rendered screen. */
export function ringHasNothingToCount(ring: Pick<RingOut, "total">): boolean {
  return !ring.total || ring.total <= 0;
}

/** "This week"'s four metric rows (package 10 review): a row that has no value is not its own
 *  line — four "Not written down yet" rows in a column read as a wall of nothing. Only a
 *  metric that actually has a value gets its own grounded `MetricRow`; every metric with none
 *  is named, once, in a single quiet line under them ("Not written down yet: steps, heart
 *  rate, sleep, water."). Pure, so which rows draw and what the one line names is a unit, not
 *  only ever seen through a rendered screen. */
export interface MetricRowsView {
  logged: MetricRowOut[];
  unloggedLabels: string[];
}
export function metricRowsView(metrics: readonly MetricRowOut[]): MetricRowsView {
  const logged: MetricRowOut[] = [];
  const unloggedLabels: string[] = [];
  for (const row of metrics) {
    if (row.status === "logged") logged.push(row);
    else unloggedLabels.push(row.label);
  }
  return { logged, unloggedLabels };
}

/** His medicines today: shown to him always, and to a key whose scope opens his medicines. */
export function medicinesShown(owner: boolean, scopes: readonly string[]): boolean {
  return owner || scopes.includes("medicines");
}

/** A key without the records scope does not open his papers — "Your papers" is shown
 *  withheld, named, never left off the screen in silence (E02-07 library part B #4). */
export function papersWithheld(scopes: readonly string[]): boolean {
  return !scopes.includes("records");
}

/** One blood pressure or blood sugar reading, read off its fact the way `systolics` reads a
 *  sparkline's numbers — the newest first, never worked out from more than the fact itself. */
export interface ReadingRow {
  at: string;
  words: string;
}

/** His blood pressures, newest first (subject `blood_pressure`, attribute `reading`,
 *  `{systolic, diastolic}` in mmHg — `app.ingestion.readings`). */
export function bloodPressureRows(facts: readonly FactOut[]): ReadingRow[] {
  return facts
    .filter((fact) => fact.subject === "blood_pressure" && fact.attribute === "reading")
    .map((fact) => {
      const value = fact.value as { systolic?: unknown; diastolic?: unknown } | null;
      const top = value?.systolic;
      const bottom = value?.diastolic;
      if (typeof top !== "number" || typeof bottom !== "number") return null;
      return { at: fact.valid_from, words: `${top}/${bottom}` };
    })
    .filter((each): each is ReadingRow => each !== null)
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/** His blood sugars, newest first (subject `blood_sugar`, attribute `reading`, `{glucose}` in
 *  mmol/L). */
export function bloodSugarRows(facts: readonly FactOut[]): ReadingRow[] {
  return facts
    .filter((fact) => fact.subject === "blood_sugar" && fact.attribute === "reading")
    .map((fact) => {
      const glucose = (fact.value as { glucose?: unknown } | null)?.glucose;
      if (typeof glucose !== "number") return null;
      return { at: fact.valid_from, words: String(glucose) };
    })
    .filter((each): each is ReadingRow => each !== null)
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

export const MEALS: readonly Meal[] = ["breakfast", "lunch", "dinner", "snack"];

/** Today's meals, one entry each at most, the latest logged for that slot — or none, when
 *  nothing was said about it: a blank day is blank (docs/recommendation-engine.md §2.7), never
 *  a row saying "not logged". */
export function mealsToday(entries: readonly FoodEntryOut[], today: Date): Partial<Record<Meal, FoodEntryOut>> {
  const day = dayKey(today);
  const found: Partial<Record<Meal, FoodEntryOut>> = {};
  for (const entry of entries) {
    if (dayKey(new Date(entry.eaten_at)) !== day) continue;
    const before = found[entry.meal];
    if (!before || Date.parse(entry.eaten_at) >= Date.parse(before.eaten_at)) found[entry.meal] = entry;
  }
  return found;
}

/** What he ate, in his own words when he typed them, else the catalogue's word for what he
 *  tapped — never a bare id on the screen. */
export function foodWords(entry: FoodEntryOut, catalog: readonly FoodCatalogItemOut[]): string {
  if (entry.food) return entry.food;
  const found = catalog.find((item) => item.id === entry.catalog_id);
  return found?.label ?? entry.catalog_id ?? "";
}
