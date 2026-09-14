import type { DecisionIn, ReviewCardOut, ReviewFieldOut } from "../api/types";
import type { Strings } from "../strings";

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

/** The value as the paper has it, for the box. */
export function valueText(value: unknown): string {
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.instruction === "string") return record.instruction;
    return Object.values(record)
      .filter((each): each is string | number => typeof each === "string" || typeof each === "number")
      .map(String)
      .join(" · ");
  }
  return "";
}

/** A number or a few words can be retyped; anything with structure cannot. */
export function canCorrect(field: Pick<ReviewFieldOut, "value">): boolean {
  return typeof field.value === "number" || typeof field.value === "string";
}

export function startingEdits(card: ReviewCardOut): Record<string, FieldEdit> {
  return Object.fromEntries(card.fields.map((field) => [field.field_id, { text: valueText(field.value), leftOut: false }]));
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

/** His words for the line, by the backend's subject and attribute codes; never the code. */
export function fieldLabel(field: Pick<ReviewFieldOut, "subject" | "attribute">, s: Strings): string {
  return s.onboarding.fields[field.subject]?.[field.attribute] ?? s.onboarding.records.otherLine;
}

/** How sure Nura is, in words: the backend's own threshold (`needs_confirm`), never a percentage. */
export function confidenceLine(field: Pick<ReviewFieldOut, "needs_confirm">, s: Strings): string {
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
    case "unknown":
      return r.kindUnknown;
  }
}

/** A card Nura could not read has nothing to say yes to. */
export function readable(card: ReviewCardOut): boolean {
  return card.document_kind !== "unknown" && card.fields.length > 0;
}
