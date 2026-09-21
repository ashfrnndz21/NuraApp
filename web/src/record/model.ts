import type {
  ArtifactRefOut,
  ClassCandidateOut,
  ClassifyOut,
  EpisodeViewOut,
  FeedItemOut,
  HomeCareCategory,
  LabelIn,
  LineOut,
  MedicineOutcome,
  ProviderSummaryOut,
  RangeOut,
  ReviewCardOut,
  RoutineDayIn,
  RoutineOut,
  SlotOut,
  TimelineItemOut,
  TrendOut,
  TrendPointOut,
} from "../api/types";
import type { Density } from "../store/session";
import { readingTally } from "../onboarding/review";
import { fill, type Strings } from "../strings";
import { timeLine } from "../today/model";
import type { HubEntry } from "./places";
import { sanitizeDisplayText } from "./sanitize";

/** The Record's logic apart from any screen, all unit-tested. Nothing here writes a sentence:
 *  every line is the backend's, or a whole line of the catalogue with a name, a date or a
 *  number in its slot. */

/** In his density the Record opens on his medicines, his papers and his day, one a screen;
 *  in hers, on what changed and the visits. */
export const PATIENT_HUB: readonly HubEntry[] = ["medicines", "papers", "routine", "timeline", "trends", "providers", "ledger", "changes"];
export const CAREGIVER_HUB: readonly HubEntry[] = ["changes", "timeline", "medicines", "papers", "trends", "routine", "providers", "ledger"];

/** The part of the papers each entry reads, so a key that does not open it is not offered it.
 *  `ledger` reads "money" (`Scope.MONEY`, the same door a policy and a claim already stand
 *  behind): a helper, a viewer, an emergency-only key and a clinic key never see the entry. */
const PART: Record<HubEntry, string | null> = {
  medicines: "medicines",
  papers: "records",
  routine: "medicines",
  timeline: "visits",
  trends: "records",
  providers: "visits",
  changes: null,
  ledger: "money",
};

export function hubEntries(density: Density, scopes: readonly string[]): HubEntry[] {
  const order = density === "patient" ? PATIENT_HUB : CAREGIVER_HUB;
  return order.filter((entry) => {
    const part = PART[entry];
    return part === null || scopes.includes(part);
  });
}

/** One of a list, for the patient density's one thing a screen. */
export function onePage<T>(items: readonly T[], index: number): { item: T | null; index: number; total: number } {
  if (items.length === 0) return { item: null, index: 0, total: 0 };
  const at = Math.max(0, Math.min(index, items.length - 1));
  return { item: items[at] ?? null, index: at, total: items.length };
}

// --- his medicines (E04-01, E04-05) ---------------------------------------------------------

/** How sure Nura is of a line, in words: a line written on a person's yes says so. */
export function confidenceLine(line: Pick<LineOut, "confidence" | "confidence_state">, s: Strings): string {
  if (line.confidence_state === "confirmed_by_person") return s.record.sureYes;
  if (line.confidence_state === "disputed") return s.record.disputed;
  return (line.confidence ?? 0) >= 0.9 ? s.record.sureRead : s.onboarding.records.check;
}

/** The questions for the doctor a line carries: its own, then each flag's, once each. */
export function lineQuestions(line: Pick<LineOut, "doctor_question" | "flags">): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const text of [...line.doctor_question, ...line.flags.flatMap((flag) => flag.question)]) {
    if (!seen.has(text)) {
      seen.add(text);
      out.push(text);
    }
  }
  return out;
}

/** The reorder card's two buttons, in the backend's words, once the count is at the
 *  threshold; none before. */
export function reorderActions(line: Pick<LineOut, "count">): { askToOrder: string; iHaveMore: string } | null {
  const actions = line.count?.reorder_actions;
  if (!line.count?.reorder_due || !actions?.ask_to_order || !actions.i_have_more) return null;
  return { askToOrder: actions.ask_to_order, iHaveMore: actions.i_have_more };
}

/** The line a feed card is about: the reorder card cites the line's fact. */
export function lineForCard(item: Pick<FeedItemOut, "why">, lines: readonly LineOut[]): LineOut | null {
  const cited = item.why.fact_ids;
  const ids = Array.isArray(cited) ? cited.map(String) : [];
  return lines.find((line) => line.fact_id !== undefined && ids.includes(line.fact_id)) ?? null;
}

/** What a label would do to the list, in one line. */
export function outcomeLine(outcome: MedicineOutcome, s: Strings): string {
  switch (outcome) {
    case "new_line":
      return s.record.outcomeNew;
    case "refill":
      return s.record.outcomeRefill;
    case "dose_change":
      return s.record.outcomeChange;
    default:
      return String(s.refusals.AlreadyRecorded);
  }
}

export function severityLine(severity: string, s: Strings): string {
  const known = s.record.severity as Record<string, string>;
  return known[severity] ?? s.record.severity.moderate;
}

function text(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return "";
}

/** A label as the photo read it, for the person to check and finish: the name, the
 *  strength with its unit, the dose line as printed, the count, the doctor. A line Nura
 *  did not read stays empty for him to type. */
export function labelFromCard(card: Pick<ReviewCardOut, "fields" | "document_kind">): LabelIn {
  const label: LabelIn = {};
  let least = 1;
  for (const field of card.fields) {
    if (field.subject !== "medicine" || field.unreadable) continue;
    const value = field.corrected_value ?? field.value;
    // A field he has since corrected is his own word, not the extractor's guess — its
    // confidence never pulls the label's own number down.
    if (field.state !== "corrected") least = Math.min(least, field.confidence);
    switch (field.attribute) {
      case "name":
        label.generic = text(value).toLowerCase() || null;
        break;
      case "strength":
        label.strength = [text(value), field.unit ?? ""].join(" ").trim() || null;
        break;
      case "dose": {
        const dose = value as { instruction?: unknown; as_printed?: unknown } | null;
        label.dose_text = text(dose?.as_printed) || text(dose?.instruction) || text(value) || null;
        break;
      }
      case "quantity":
        label.quantity = typeof value === "number" ? value : Number(text(value)) || null;
        break;
      case "prescriber":
        label.prescriber = text(value) || null;
        break;
    }
  }
  // Never below the register's own floor for a loose pill's guess (`PILL_MAX_CONFIDENCE`,
  // `app.ingestion.review`): the backend caps this again regardless of what is sent, but the
  // number shown to him before that round trip should already tell the truth.
  if (card.document_kind === "pill_photo") least = Math.min(least, 0.79);
  label.confidence = least;
  return label;
}

/** A label he can ask about: a name and how to take it, the rest as typed. */
export function tidyLabel(label: LabelIn): LabelIn | null {
  const generic = label.generic?.trim().toLowerCase();
  const doseText = label.dose_text?.trim();
  if (!generic || !doseText) return null;
  const quantity = label.quantity && label.quantity > 0 ? Math.min(Math.round(label.quantity), 2000) : null;
  return {
    generic,
    strength: label.strength?.trim() || null,
    form: label.form?.trim() || null,
    dose_text: doseText,
    quantity,
    prescriber: label.prescriber?.trim() || null,
    confidence: label.confidence,
  };
}

/** A whole number of tablets found at home, or nothing. */
export function countOf(typed: string): number | null {
  const trimmed = typed.trim();
  if (!/^\d{1,4}$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= 1 && value <= 1000 ? value : null;
}

// --- "Your tablets" — the registry (redesign package 11) ----------------------------------

function upper1(text: string): string {
  return text.length > 0 ? text[0]!.toUpperCase() + text.slice(1) : text;
}

/** The anchor words already in the catalogue ("Breakfast", "Bedtime", …), in his day's
 *  order — never new prose, the same words `s.record.anchors` already carries elsewhere. */
export function doseAnchorWords(line: Pick<LineOut, "dose">, s: Strings): string[] {
  const known = s.record.anchors as Record<string, string>;
  return line.dose.anchors.map((anchor) => known[anchor] ?? anchor);
}

/** "1 tablet", "0.5 mL" — the amount and its own unit, exactly as the line holds them, no
 *  word invented: absent when there is no amount to say (a dose with none on file). */
export function doseAmountLine(line: Pick<LineOut, "dose">): string | null {
  if (!(line.dose.amount > 0)) return null;
  return `${numberText(line.dose.amount)} ${line.dose.unit}`.trim();
}

/** One registry row's fields, built only from what the line actually holds (redesign
 *  package 11): his word for it first, the chemical name and strength second and small,
 *  the form, how many and when, how many are left when the backend has ever dispensed any,
 *  and where it came from with its date. A field the record does not hold is `null` here,
 *  never a placeholder — the caller renders nothing for it, never a blank or a dash. */
export interface RegistryRow {
  name: string;
  chemical: string;
  form: string | null;
  howMany: string | null;
  supplyLines: string[];
  source: string | null;
  monthlyCost: string | null;
  highRisk: boolean;
  duplicate: boolean;
}

export function registryRow(line: LineOut, s: Strings): RegistryRow {
  const anchors = doseAnchorWords(line, s);
  const amount = doseAmountLine(line);
  const howMany = amount && anchors.length > 0 ? `${amount} · ${anchors.join(", ")}` : (amount ?? (anchors.length > 0 ? anchors.join(", ") : null));
  return {
    name: upper1(line.name),
    chemical: [line.generic, line.strength].filter((each) => each.length > 0).join(" "),
    form: line.form.length > 0 ? upper1(line.form) : null,
    howMany,
    supplyLines: line.count?.lines ?? [],
    source: line.source.length > 0 ? line.source : null,
    monthlyCost: line.monthly_cost_said ?? null,
    highRisk: line.high_risk,
    duplicate: (line.duplicate_of?.length ?? 0) > 0,
  };
}

/** Today's dose cards (`GET …/medicines/today`), grouped under the registry line each is
 *  for — "Today" first, before the registry itself (redesign package 11), reading the same
 *  endpoint and the same tap the existing Taken flow already uses (`nura.dosesToday`,
 *  `nura.taken`): nothing here re-plumbs it, only shows it. */
export function slotsForLine(lineId: string, slots: readonly SlotOut[]): SlotOut[] {
  return slots.filter((slot) => slot.line_id === lineId);
}

// --- add a medicine: the which-one question (redesign package 11, #302) -------------------

/** What the class question needs to ask, decided from the register's own answer alone
 *  (`GET …/medicines/classify`) — never from the extracted text. `"none"` when the name is
 *  either a specific medicine or simply unknown to the register: either way, nothing to ask
 *  here (an unknown name is still handled downstream, by the ordinary `NotIdentified`
 *  refusal). `"ask"` only when the register itself filed products under this name as a
 *  class, with at least one member to offer as a choice. */
export type ClassQuestion = { kind: "none" } | { kind: "ask"; candidates: ClassCandidateOut[] };

export function classQuestionFor(found: Pick<ClassifyOut, "name_kind" | "candidates">): ClassQuestion {
  if (found.name_kind === "class" && found.candidates.length > 0) {
    return { kind: "ask", candidates: found.candidates };
  }
  return { kind: "none" };
}

// --- add a medicine: typed entry, one field at a time (redesign package 11) ---------------

export type TypedEntryField = "generic" | "strength" | "form" | "dose_text";

/** The next field the short typed form still needs, in the order the owner asked for it —
 *  "name → strength → form → how many, when" — or `null` once every field the backend
 *  requires (`LabelIn`) is filled and the form may check the name. Quantity and prescriber
 *  are optional, so they are never named here. */
export function nextTypedField(label: LabelIn): TypedEntryField | null {
  if (!label.generic?.trim()) return "generic";
  if (!label.strength?.trim()) return "strength";
  if (!label.form?.trim()) return "form";
  if (!label.dose_text?.trim()) return "dose_text";
  return null;
}

/** A field an extractor wrote, or a name he typed, shown on a confirmation card before he
 *  has said anything about it: hostile until he says yes (redesign package 11). Control and
 *  bidi characters folded away, long text capped — see `record/sanitize.ts` for exactly
 *  what and why. This is the one function any card must run such a field's text through. */
export function displayExtractedText(raw: string | null | undefined): string {
  return sanitizeDisplayText(raw);
}

// --- the timeline, an illness, the directory (E03-01..03) --------------------------------------

/** The visit's doctor, or the illness's own name. */
export function itemTitle(item: Pick<TimelineItemOut, "kind" | "provider" | "episode">): string {
  return item.kind === "episode" ? (item.episode?.label ?? "") : (item.provider?.name ?? "");
}

/** How much hangs off a visit or an illness, in whole lines. */
export function hangingLines(item: Pick<TimelineItemOut, "artifacts" | "facts">, s: Strings): string[] {
  const papers = item.artifacts.length;
  const facts = item.facts.length;
  const lines = [papers === 0 ? s.record.nothingWith : papers === 1 ? s.record.paperWith : fill(s.record.papersWith, { count: papers })];
  if (facts === 1) lines.push(s.record.factWith);
  else if (facts > 1) lines.push(fill(s.record.factsWith, { count: facts }));
  return lines;
}

export function visitStatusLine(status: string, s: Strings): string | null {
  const known = s.record.status as Record<string, string>;
  return known[status] ?? null;
}

/** A paper by reference: a photo, a letter (a PDF), or another paper, and its day. */
export function artifactLine(artifact: Pick<ArtifactRefOut, "kind">, date: string, s: Strings): string {
  const template = artifact.kind === "photo" ? s.record.photoOn : artifact.kind === "pdf" ? s.record.letterOn : s.record.paperOn;
  return fill(template, { date });
}

/** A moment during an illness as one whole line by its kind, never its label (a label is a
 *  name for the moment in the backend's own code and can carry a medicine's chemical name). */
export function momentLine(kind: string, date: string, s: Strings): string {
  const known = s.record.moments as Record<string, string>;
  return fill(known[kind] ?? s.record.moments.other, { date });
}

// --- "Your papers" (library part B #2): the full list, under Health and under the Record ----

export interface PaperStateChip {
  label: string;
  /** `Flag`'s own state, or `null` for plain text — "Read" is never a judgement, so it never
   *  wears the amber/sage/question chip the other three states do. */
  state: "ok" | "attention" | "question" | null;
}

/** One paper's state chip: "Check" (the question flag) while it waits for his yes — the same
 *  meaning as the review card's own "Check this one", in the list's shorter word; a
 *  confirmed lab report with any of its own printed ranges to compare against, "{n} outside"
 *  (amber) or "All in range" (sage), from `rangeStatus` alone, never a re-judgement of ours;
 *  any other confirmed kind, or a lab report with nothing parsable on it, the plain "Read" —
 *  never re-checked once he has said yes to it. */
export function paperStateChip(card: Pick<ReviewCardOut, "confirmed_at" | "document_kind" | "fields">, s: Strings): PaperStateChip {
  if (!card.confirmed_at) return { label: s.record.paperChipCheck, state: "question" };
  if (card.document_kind === "lab_report") {
    const { outside, parsable } = readingTally(card as ReviewCardOut);
    if (parsable > 0) {
      return outside > 0 ? { label: fill(s.record.paperChipOutside, { n: outside }), state: "attention" } : { label: s.record.paperChipInRange, state: "ok" };
    }
  }
  return { label: s.record.paperChipRead, state: null };
}

export interface PaperYearGroup {
  year: number;
  cards: ReviewCardOut[];
}

/** The year the full list groups a paper under: the paper's own printed date when there is
 *  one, else the day it came in — never a guess. */
export function paperYearOf(card: Pick<ReviewCardOut, "document_date" | "created_at">): number {
  return new Date(card.document_date ?? card.created_at).getFullYear();
}

/** The full list, grouped by year once there are enough papers to need it (more than a
 *  screenful, eight) — an empty array below that, so the caller renders the same cards flat.
 *  The caller's own order (newest first) is kept inside each group. */
export function groupPapersByYear(cards: readonly ReviewCardOut[]): PaperYearGroup[] {
  if (cards.length <= 8) return [];
  const groups: PaperYearGroup[] = [];
  for (const card of cards) {
    const year = paperYearOf(card);
    const last = groups[groups.length - 1];
    if (last && last.year === year) last.cards.push(card);
    else groups.push({ year, cards: [card] });
  }
  return groups;
}

/** The confirmed papers that are not with this illness yet: what the chief may put with it. */
export function papersToPut(cards: readonly ReviewCardOut[], view: Pick<EpisodeViewOut, "episode" | "visits">): ReviewCardOut[] {
  const there = new Set([...view.episode.artifacts, ...view.visits.flatMap((visit) => visit.artifacts)].map((each) => each.artifact_id));
  const seen = new Set<string>();
  return cards.filter((card) => {
    if (!card.confirmed_at || there.has(card.artifact_id) || seen.has(card.artifact_id)) return false;
    seen.add(card.artifact_id);
    return true;
  });
}

export function providerLines(summary: ProviderSummaryOut, dateOf: (iso: string) => string, s: Strings): string[] {
  const lines = [summary.visits === 1 ? s.record.visitsOne : fill(s.record.visitsMany, { count: summary.visits })];
  if (summary.last_visit) lines.push(fill(s.record.lastVisit, { date: dateOf(summary.last_visit.scheduled_at) }));
  if (summary.next_visit) lines.push(fill(s.record.nextVisit, { date: dateOf(summary.next_visit.scheduled_at) }));
  return lines;
}

export function kindWord(kind: string, s: Strings): string {
  const known = s.record.kind as Record<string, string>;
  return known[kind] ?? s.record.kind.other;
}

/** One of Services' four "Help at home" tiles, in his own words (`s.homeCare`). */
export function homeCareCategoryLabel(category: HomeCareCategory, s: Strings): string {
  return s.homeCare[category];
}

// --- a lab trend (E09-01) ---------------------------------------------------------------------

export const ANALYTES = ["total_cholesterol", "ldl", "hdl", "triglycerides", "hba1c", "creatinine", "egfr", "potassium", "haemoglobin", "tsh"] as const;
export type Analyte = (typeof ANALYTES)[number];

/** A number as the paper printed it: no trailing zeros, no rounding of what was read. */
export function numberText(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
}

/** The range a result was placed against, as a whole line in his words ("For most people
 *  this number is under 200."). The unit is hers, not his (plain words, rule 12): it is added
 *  only when `units` is asked for, in the caregiver's density. */
export function rangeLine(range: RangeOut | null, s: Strings, units = false): string {
  if (!range || (range.lower === null && range.upper === null)) return s.record.noRange;
  const unit = units && range.unit ? ` ${range.unit}` : "";
  if (range.lower === null) return fill(s.record.rangeUnder, { upper: `${numberText(range.upper!)}${unit}` });
  if (range.upper === null) return fill(s.record.rangeOver, { lower: `${numberText(range.lower)}${unit}` });
  return fill(s.record.rangeBetween, { lower: numberText(range.lower), upper: `${numberText(range.upper)}${unit}` });
}

/** A clock time of his day ("07:00", "19:30") said the way every time in the app is said,
 *  through `timeLine`: "7:00 am" in English, "07:00" in Malay and Chinese — one time format
 *  everywhere (plain words, rule 13). Anything that is not a time is left as it is. */
export function clockLine(hhmm: string, locale: string): string {
  const match = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!match) return hhmm;
  return timeLine(new Date(2000, 0, 1, Number(match[1]), Number(match[2])), locale);
}

/** One result's range line: its range, or — when the backend placed it against none — why
 *  not, in his words (`no_range_because`: his age or whether he is a man or a woman is
 *  needed, or there is none on file). A reason the strings do not know says there is none. */
export function pointRangeLine(point: Pick<TrendPointOut, "range" | "no_range_because">, s: Strings, units = false): string {
  if (point.range === null && point.no_range_because) {
    const known = s.record.noRangeBecause as Record<string, string>;
    return known[point.no_range_because] ?? s.record.noRange;
  }
  return rangeLine(point.range, s, units);
}

/** Whose range: the lab's own printed on his paper, or the guideline row for his age. The
 *  backend says which in `source`; nothing is read into the id. */
export function rangeSourceLine(range: RangeOut | null, s: Strings): string | null {
  if (!range) return null;
  return range.source === "lab" ? s.record.labRange : s.record.guideRange;
}

/** The trend's lines apart from its boundary, and the boundary, last, as the backend wrote
 *  both: the boundary is never shown above a line. */
export function trendLines(trend: Pick<TrendOut, "lines" | "boundary">): { body: string[]; boundary: string[] } {
  const said = trend.boundary
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const inBoundary = new Set(said);
  const body = trend.lines.filter((line) => !inBoundary.has(line.trim()));
  const tail = trend.lines.filter((line) => inBoundary.has(line.trim()));
  return { body, boundary: tail.length > 0 ? tail : said };
}

// --- the day (E10-01) -------------------------------------------------------------------------

export const ANCHORS = ["wake", "breakfast", "lunch", "dinner", "bed"] as const;
export type AnchorName = (typeof ANCHORS)[number];
export const READINGS = ["blood_pressure", "blood_sugar", "weight"] as const;
export type ReadingName = (typeof READINGS)[number];

/** The day as it is set now, to change: her builder starts from it. */
export function dayOf(routine: Pick<RoutineOut, "anchors" | "reading_prompts" | "walks" | "morning_card_at">): RoutineDayIn {
  return {
    anchors: Object.fromEntries(ANCHORS.map((anchor) => [anchor, routine.anchors[anchor] ?? ""])),
    reading_prompts: (routine.reading_prompts ?? []).filter((p) => p.length === 2).map((p) => [p[0]!, p[1]!] as [string, string]),
    walks: [...routine.walks],
    morning_card_at: routine.morning_card_at,
  };
}

export function withTime(day: RoutineDayIn, anchor: AnchorName, at: string): RoutineDayIn {
  return { ...day, anchors: { ...day.anchors, [anchor]: at } };
}

export function withReading(day: RoutineDayIn, reading: ReadingName, anchor: AnchorName, on: boolean): RoutineDayIn {
  const rest = day.reading_prompts.filter(([code, at]) => !(code === reading && at === anchor));
  const prompts = on ? [...rest, [reading, anchor] as [string, string]] : rest;
  // In the order of his day, so the yes and the write see the same day.
  prompts.sort((a, b) => ANCHORS.indexOf(a[1] as AnchorName) - ANCHORS.indexOf(b[1] as AnchorName) || a[0].localeCompare(b[0]));
  return { ...day, reading_prompts: prompts };
}

export function withWalk(day: RoutineDayIn, anchor: AnchorName, on: boolean): RoutineDayIn {
  const rest = day.walks.filter((each) => each !== anchor);
  const walks = on ? [...rest, anchor] : rest;
  walks.sort((a, b) => ANCHORS.indexOf(a as AnchorName) - ANCHORS.indexOf(b as AnchorName));
  return { ...day, walks };
}

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Five times, each a clock time, rising through the day, and the Today page's time. The
 *  backend refuses anything else (`NotARoutine`); this only keeps the button from asking. */
export function dayInOrder(day: RoutineDayIn): boolean {
  const times = ANCHORS.map((anchor) => day.anchors[anchor] ?? "");
  if (!times.every((at) => HHMM.test(at)) || !HHMM.test(day.morning_card_at)) return false;
  return times.every((at, index) => index === 0 || at > times[index - 1]!);
}
