import type { DecisionIn, FieldRange, ReviewCardOut, ReviewFieldOut } from "../api/types";
import { fill, type Strings } from "../strings";

/** The capture review card (E02-07) as the onboarding records step shows it: what each line
 *  of the paper was read as, how sure Nura is in plain words, a place to correct it, and one
 *  "Looks right" that sends a decision for every field. Pure (`tests/unit/review.test.ts`).
 *
 *  Nothing here interprets a value. A number is shown as the paper has it, and a correction
 *  is only ever the number or words he typed; a structured value (a dose instruction) cannot
 *  be retyped here — he leaves it out if it is wrong, and nothing is guessed in its place. */

export interface FieldEdit {
  /** What the correction box holds; starts as the value as read. */
  text: string;
  leftOut: boolean;
}

/** The value as the paper has it, for the box: every shape the API can send — a number, a
 *  string, a boolean, the `{instruction}` shape, an array, or any other small structure —
 *  read as far down into it as there is anything to read. Empty only when there is truly
 *  nothing readable in the value at all (`null`, `undefined`, or a wholly empty structure);
 *  the review card never shows that as a blank line — it shows `readableValueText`'s own
 *  words instead (E02 defect #2, "some lines showed NO value at all"). */
export function valueText(value: unknown): string {
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  // Not localised: a boolean is rare here (a pill's "can it be split", say) and this
  // function only ever renders the paper's own words, in no particular language — his own
  // words for the field are `fieldLabel`'s job, in his language, not this one's.
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    return value
      .map((each) => valueText(each))
      .filter((each) => each.length > 0)
      .join(" · ");
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.instruction === "string" && record.instruction.trim()) return record.instruction;
    return Object.values(record)
      .map((each) => valueText(each))
      .filter((each) => each.length > 0)
      .join(" · ");
  }
  return "";
}

/** `valueText`, or Nura's own words when there is nothing readable in the value at all: a
 *  field the review card shows is never a blank line (E02 defect #2). Distinct from
 *  `field.unreadable` (E02-02's own "Nura could not read this one, please type it"): this is
 *  for a value that did come back from the extractor, just in a shape nothing here can turn
 *  into readable text. */
export function readableValueText(value: unknown, s: Strings): string {
  const text = valueText(value);
  return text.length > 0 ? text : s.onboarding.records.valueUnreadable;
}

/** Where a number sits against the paper's own printed range (never a judgement of ours,
 *  and never the app's own guideline range, `app.reasoning.ranges` — only ever what this
 *  paper prints beside this result): "under" is exclusive of an upper-only range, "or more"
 *  is inclusive of a lower-only one, and a two-sided range is inclusive at both ends, the way
 *  the paper prints them (matches `app.reasoning.ranges.Range.band_of`). `"unknown"` for
 *  anything that is not a plain number, no range at all, or a range with neither bound
 *  readable off its text (E02 defect #3).
 *
 *  Invariant this relies on: `value` and `range` are read off the same printed row, so they
 *  are always in the same unit here — nothing here converts one. If a future change ever
 *  lets a value and its range come from different rows, or a value gets converted to a
 *  different unit before this is called, this comparison has to be revisited alongside it. */
export function rangeStatus(
  value: unknown,
  range: Pick<FieldRange, "low" | "high"> | null | undefined,
): "above" | "below" | "in" | "unknown" {
  if (typeof value !== "number" || !range) return "unknown";
  const { low, high } = range;
  if (low != null && high != null) {
    if (value < low) return "below";
    return value > high ? "above" : "in";
  }
  if (high != null) return value < high ? "in" : "above";
  if (low != null) return value >= low ? "in" : "below";
  return "unknown";
}

/** A number or a few words can be retyped, and a line Nura could not read must be; anything
 *  with structure cannot. */
export function canCorrect(field: Pick<ReviewFieldOut, "value" | "unreadable">): boolean {
  return field.unreadable || typeof field.value === "number" || typeof field.value === "string";
}

export function startingEdits(card: ReviewCardOut): Record<string, FieldEdit> {
  return Object.fromEntries(
    card.fields.map((field) => [field.field_id, { text: field.unreadable ? "" : valueText(field.value), leftOut: false }]),
  );
}

/** "231", "231.5", "231,5" → a number; anything else is not one. */
export function parseNumber(text: string): number | null {
  const cleaned = text.trim().replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
  return Number(cleaned);
}

export type Decided = { ok: true; decision: DecisionIn } | { ok: false; field_id: string };

/** His decision on one field: left out → rejected; unchanged → confirmed; retyped → corrected
 *  to exactly what he typed (a number stays a number). An empty box or a word where a number
 *  was read is not a decision yet. */
export function decide(field: ReviewFieldOut, edit: FieldEdit | undefined): Decided {
  const field_id = field.field_id;
  if (!edit) return { ok: true, decision: { field_id, decision: "confirmed" } };
  if (edit.leftOut) return { ok: true, decision: { field_id, decision: "rejected" } };
  if (field.unreadable) {
    // Never confirmed as read (the backend refuses it): what he typed, or nothing yet.
    const typed = edit.text.trim();
    if (typed.length === 0) return { ok: false, field_id };
    return { ok: true, decision: { field_id, decision: "corrected", corrected_value: parseNumber(typed) ?? typed } };
  }
  if (!canCorrect(field)) return { ok: true, decision: { field_id, decision: "confirmed" } };
  const typed = edit.text.trim();
  if (typed === valueText(field.value).trim()) return { ok: true, decision: { field_id, decision: "confirmed" } };
  if (typed.length === 0) return { ok: false, field_id };
  if (typeof field.value === "number") {
    const number = parseNumber(typed);
    if (number === null) return { ok: false, field_id };
    if (number === field.value) return { ok: true, decision: { field_id, decision: "confirmed" } };
    return { ok: true, decision: { field_id, decision: "corrected", corrected_value: number } };
  }
  return { ok: true, decision: { field_id, decision: "corrected", corrected_value: typed } };
}

/** Every field decided, in the card's order — the backend needs one decision per field — or
 *  the fields that still need him. */
export function decisionsFor(card: ReviewCardOut, edits: Record<string, FieldEdit>): { decisions: DecisionIn[]; waiting: string[] } {
  const decisions: DecisionIn[] = [];
  const waiting: string[] = [];
  for (const field of [...card.fields].sort((a, b) => a.position - b.position)) {
    const decided = decide(field, edits[field.field_id]);
    if (decided.ok) decisions.push(decided.decision);
    else waiting.push(decided.field_id);
  }
  return { decisions, waiting };
}

/** A pharmacy receipt's line subjects are numbered in the order printed (`item_1`,
 *  `item_2`…) — every one of them shares one set of words (`s.onboarding.fields.item`). */
const ITEM_SUBJECT = /^item_\d+$/;

/** His words for the line: the canonical label for the backend's subject and attribute codes
 *  when Nura knows one; failing that, the paper's own words for the line (`label_on_paper` —
 *  always given for a line outside the controlled vocabulary, `attribute === "other"`); only
 *  when neither is there, a generic line name. Never the bare code either way. */
export function fieldLabel(
  field: Pick<ReviewFieldOut, "subject" | "attribute"> & { label_on_paper?: string | null },
  s: Strings,
): string {
  const subject = ITEM_SUBJECT.test(field.subject) ? "item" : field.subject;
  const known = s.onboarding.fields[subject]?.[field.attribute];
  if (known) return known;
  const printed = field.label_on_paper?.trim();
  return printed && printed.length > 0 ? printed : s.onboarding.records.otherLine;
}

/** How sure Nura is, in words: the backend's own threshold (`needs_confirm`), never a percentage. */
export function confidenceLine(field: Pick<ReviewFieldOut, "needs_confirm" | "unreadable">, s: Strings): string {
  if (field.unreadable) return s.onboarding.records.unreadable;
  return field.needs_confirm ? s.onboarding.records.check : s.onboarding.records.sure;
}

export function kindLine(kind: ReviewCardOut["document_kind"], s: Strings): string {
  const r = s.onboarding.records;
  switch (kind) {
    case "lab_report":
      return r.kindLabReport;
    case "medicine_label":
      return r.kindMedicineLabel;
    case "discharge_letter":
      return r.kindDischargeLetter;
    case "clinic_slip":
      return r.kindClinicSlip;
    case "handwritten_prescription":
      return r.kindHandwritten;
    case "insurance_letter":
      return r.kindInsuranceLetter;
    case "insurance_policy":
      return r.kindInsurancePolicy;
    case "insurance_claim":
      return r.kindInsuranceClaim;
    case "device_screen":
      return r.kindDeviceScreen;
    case "pill_photo":
      return r.kindPillPhoto;
    case "pharmacy_receipt":
      return r.kindPharmacyReceipt;
    case "other":
      return r.kindOther;
    case "not_health":
    case "unknown":
    case "unsupported_file_type":
      return r.kindUnknown;
  }
}

/** The report table's own short title for the kind of paper (blueprint `report`'s `head('Blood
 *  test', ...)`): a name, not the sentence `kindLine` reads out loud ("This is a blood
 *  test."). */
export function kindTitle(kind: ReviewCardOut["document_kind"], s: Strings): string {
  const r = s.onboarding.records;
  switch (kind) {
    case "lab_report":
      return r.titleLabReport;
    case "medicine_label":
      return r.titleMedicineLabel;
    case "discharge_letter":
      return r.titleDischargeLetter;
    case "clinic_slip":
      return r.titleClinicSlip;
    case "handwritten_prescription":
      return r.titleHandwritten;
    case "insurance_letter":
      return r.titleInsuranceLetter;
    case "insurance_policy":
      return r.titleInsurancePolicy;
    case "insurance_claim":
      return r.titleInsuranceClaim;
    case "device_screen":
      return r.titleDeviceScreen;
    case "pill_photo":
      return r.titlePillPhoto;
    case "pharmacy_receipt":
      return r.titlePharmacyReceipt;
    case "other":
      return r.titleOtherKind;
    case "not_health":
    case "unknown":
    case "unsupported_file_type":
      return r.titleUnknown;
  }
}

/** The header field a lab-style report's facility line is on, when the card has one — kept out
 *  of the ordinary rows once it is shown in the report's own header (blueprint `report`'s
 *  "12 September 2026 · Sunrise Medical Laboratory"), never shown twice. */
export function facilityField(card: ReviewCardOut): ReviewFieldOut | null {
  return card.fields.find((field) => field.subject === "lab_report" && (field.attribute === "facility" || field.attribute === "lab")) ?? null;
}

export interface RangeBarGeometry {
  bandStart: number;
  bandWidth: number;
  markerAt: number;
}

/** Where the paper's own printed range sits on a 0-100 bar, and where the reading's own
 *  marker falls on it (`RangeBar`'s props) — `null` whenever `rangeStatus` itself would be
 *  `"unknown"` (not a plain number, no range at all, or neither bound readable off it): a bar
 *  is never drawn for a line that has nothing to draw it against. A two-sided range is padded
 *  a third of its own width either side so the marker is never flush with the bar's edge; a
 *  one-sided range opens toward 0 (an upper-only "below X") or toward the far edge (a
 *  lower-only "X or more") — "a one-sided segment", never a second bound this row's paper
 *  never printed. */
export function rangeBarGeometry(value: unknown, range: Pick<FieldRange, "low" | "high"> | null | undefined): RangeBarGeometry | null {
  if (rangeStatus(value, range) === "unknown" || typeof value !== "number" || !range) return null;
  const { low, high } = range;
  const at = (n: number, min: number, max: number) => Math.max(0, Math.min(100, ((n - min) / (max - min)) * 100));
  if (low != null && high != null) {
    const pad = Math.max((high - low) * 0.4, (high - low || 1) * 0.4, 0.0001);
    const min = Math.min(low, value) - pad;
    const max = Math.max(high, value) + pad;
    return { bandStart: at(low, min, max), bandWidth: at(high, min, max) - at(low, min, max), markerAt: at(value, min, max) };
  }
  if (high != null) {
    // Upper-only ("below 5.2"): the in-range band runs from the bar's own open edge to `high`.
    const max = Math.max(high, value) * 1.15 || 1;
    return { bandStart: 0, bandWidth: at(high, 0, max), markerAt: at(value, 0, max) };
  }
  // Lower-only ("1.0 or more"): the band runs from `low` to the bar's own far edge.
  const max = Math.max((low ?? 0) * 2, value) * 1.15 || 1;
  const start = at(low!, 0, max);
  return { bandStart: start, bandWidth: 100 - start, markerAt: at(value, 0, max) };
}

/** The reading's own tone for the bar and the flag — sage when it is inside the paper's own
 *  range, amber when it is outside, and neither when there is nothing to compare it against. */
export function flagTone(status: ReturnType<typeof rangeStatus>): "ok" | "attention" | null {
  if (status === "in") return "ok";
  if (status === "above" || status === "below") return "attention";
  return null;
}

/** The backend's own word for where a reading sits, never invented here: "Above", "Below",
 *  "In range" — `null` where `rangeStatus` is `"unknown"` (no flag at all, E02 defect #3: a
 *  line with a range nobody can parse gets neither a bar nor a judgement). */
export function flagWord(status: ReturnType<typeof rangeStatus>, s: Strings): string | null {
  const r = s.onboarding.records;
  if (status === "above") return r.flagAbove;
  if (status === "below") return r.flagBelow;
  if (status === "in") return r.flagInRange;
  return null;
}

export interface ReadingTally {
  /** Rows whose reading falls outside the paper's own printed range ("above"/"below"). */
  outside: number;
  /** Rows whose reading falls inside it. */
  inRange: number;
  /** `outside + inRange` — rows with a range Nura could actually compare against (`m`). */
  parsable: number;
  /** Every field on the card, parsable range or not. */
  totalFields: number;
  /** Rows still waiting on him: `needs_confirm` or `unreadable`. */
  check: number;
}

export function readingTally(card: ReviewCardOut): ReadingTally {
  let outside = 0;
  let inRange = 0;
  let check = 0;
  for (const field of card.fields) {
    const status = rangeStatus(field.value, field.range);
    if (status === "above" || status === "below") outside++;
    else if (status === "in") inRange++;
    if (field.needs_confirm || field.unreadable) check++;
  }
  return { outside, inRange, parsable: outside + inRange, totalFields: card.fields.length, check };
}

/** The one headline the reading screen streams in, chosen from the card Nura really read
 *  (never invented, never a fixed sentence): a lab report with printed ranges says how many of
 *  them are outside; every one inside gets its own sentence rather than "0 of {m}"; a paper
 *  with nothing parsable — another kind of document, or a lab report with no printed ranges at
 *  all — falls back to a plain count of lines. */
export function readingHeadline(card: ReviewCardOut, s: Strings): string {
  const r = s.onboarding.records;
  const { outside, parsable, totalFields } = readingTally(card);
  if (parsable === 0) return fill(r.readingLinesRead, { m: totalFields });
  if (outside === 0) return fill(r.readingAllInRange, { m: parsable });
  return fill(r.readingSomeOutside, { n: outside, m: parsable });
}

export interface ReadingChip {
  key: "outside" | "inRange" | "check";
  label: string;
}

/** The filter chips the reading screen assembles one by one, under the headline — only the
 *  ones with something in them (E02: never "Check 0"). */
export function readingChips(card: ReviewCardOut, s: Strings): ReadingChip[] {
  const r = s.onboarding.records;
  const { outside, inRange, check } = readingTally(card);
  const chips: ReadingChip[] = [];
  if (outside > 0) chips.push({ key: "outside", label: fill(r.chipOutside, { n: outside }) });
  if (inRange > 0) chips.push({ key: "inRange", label: fill(r.chipInRange, { n: inRange }) });
  if (check > 0) chips.push({ key: "check", label: fill(r.chipCheck, { n: check }) });
  return chips;
}

export interface ReportRowView {
  fieldId: string;
  /** His own plain word for the line (`fieldLabel`). */
  label: string;
  /** The paper's own printed word for it, shown small under `label` — only when it says
   *  something `label` does not already say. */
  printedLabel: string | null;
  /** Never blank (`readableValueText`): a field the table shows always has something to read. */
  valueText: string;
  unit: string | null;
  status: ReturnType<typeof rangeStatus>;
  /** The bar's own geometry, or nothing to draw one against. */
  geometry: RangeBarGeometry | null;
  /** "Above" / "Below" / "In range", or no flag at all for an unparsable range. */
  flagWord: string | null;
  /** The bar and flag's shared tone — sage or amber, never guessed independently by a caller. */
  tone: "ok" | "attention" | null;
  /** The range exactly as the paper prints it, shown whether or not a bar could be drawn. */
  rangeText: string | null;
  /** Whether this line asks for him: `needs_confirm` or `unreadable` — the only rows that show
   *  "Check this one" and open the correction sheet on their own. */
  needsAttention: boolean;
  /** Whether a tap on the value can retype it at all (`canCorrect`). */
  correctable: boolean;
  unreadable: boolean;
}

/** One row of the report table, in full — everything a `ReportRow` needs to draw, computed
 *  once so the component itself only ever renders what this says (E02: "no row ever blank",
 *  "Check this one" only on `needs_confirm`/`unreadable`). */
export function reportRow(field: ReviewFieldOut, s: Strings): ReportRowView {
  const label = fieldLabel(field, s);
  const printed = field.label_on_paper?.trim() || null;
  const status = rangeStatus(field.value, field.range);
  return {
    fieldId: field.field_id,
    label,
    printedLabel: printed && printed !== label ? printed : null,
    valueText: readableValueText(field.value, s),
    unit: field.unit,
    status,
    geometry: rangeBarGeometry(field.value, field.range),
    flagWord: flagWord(status, s),
    tone: flagTone(status),
    rangeText: field.range?.text ?? null,
    needsAttention: field.needs_confirm || field.unreadable,
    correctable: canCorrect(field),
    unreadable: field.unreadable,
  };
}

/** The provenance line the table shows once, under every row, when every field came from the
 *  same page (or the paper had no pages at all — a single photo): `null` when the fields on
 *  this card came from different pages, so the caller falls back to `provenanceLine` per row
 *  instead (E02: "shown once ... or per row only when pages differ"). */
export function sharedProvenance(card: ReviewCardOut, dateText: string, s: Strings): string | null {
  const r = s.onboarding.records;
  const pages = new Set(card.fields.map((field) => field.page));
  if (pages.size > 1) return null;
  const page = card.fields[0]?.page ?? null;
  return page == null ? fill(r.fromPaperOn, { date: dateText }) : fill(r.fromPageAndDate, { page, date: dateText });
}

/** A pill photo's proposal, from the drug it was matched against at read time: "This looks
 *  like paracetamol 500 mg — check with the pharmacist." Never higher than a proposal — the
 *  backend holds the field's own confidence below the confirmation threshold either way
 *  (`app.ingestion.review.PILL_MAX_CONFIDENCE`), so this is shown beside the ordinary field,
 *  not in place of it. Null where a pill photo carried no guess at all (nothing recognised). */
export function pillProposalLine(card: ReviewCardOut, s: Strings): string | null {
  if (card.document_kind !== "pill_photo") return null;
  const name = card.fields.find((field) => field.subject === "medicine" && field.attribute === "name");
  if (!name || typeof name.value !== "string") return null;
  const strength = card.fields.find((field) => field.subject === "medicine" && field.attribute === "strength");
  const strengthText = strength && typeof strength.value === "string" ? ` ${strength.value}` : "";
  return fill(s.onboarding.records.pillProposal, { medicine: `${name.value}${strengthText}` });
}

/** Where a field came from, in plain words, when the paper had more than one page: "From
 *  page {page} of this paper." Nothing is shown for a single-page photo (`field.page` is
 *  only set for a PDF of several pages). */
export function provenanceLine(field: Pick<ReviewFieldOut, "page">, s: Strings): string | null {
  if (field.page == null) return null;
  return fill(s.onboarding.records.fromPage, { page: field.page });
}

/** A card Nura could not read, a page that is not a health paper, or a kind of photo Nura
 *  never opened at all, has nothing to say yes to. */
export function readable(card: ReviewCardOut): boolean {
  return (
    card.document_kind !== "unknown" &&
    card.document_kind !== "not_health" &&
    card.document_kind !== "unsupported_file_type" &&
    card.fields.length > 0
  );
}

/** The spoken twin of one line of the card, in the patient density: what the line is, what
 *  was read (or the backend's own prompt where nothing could be), and how sure Nura is. */
export function spokenLine(field: ReviewFieldOut, s: Strings): string[] {
  const label = fieldLabel(field, s);
  if (field.unreadable) return [label, ...(field.prompt ?? [s.onboarding.records.typeIt])];
  const text = valueText(field.value);
  if (text.length === 0) return [label, s.onboarding.records.valueUnreadable, confidenceLine(field, s)];
  const unit = field.unit ? ` ${field.unit}` : "";
  return [label, `${text}${unit}`, confidenceLine(field, s)];
}
