/**
 * `ReviewCardOut` / `ReviewFieldOut` / `ReviewClarifyOut`
 * (`backend/app/channels/api/schemas.py`, confirmed against the running
 * dev server's `/openapi.json`). This is the shape the report table (C3)
 * and the whose-paper/duplicate question (C2) read — never a screen's
 * own re-shaping of it.
 */

/** A guess at what kind of paper this is, shown on the card — never a fact (backend's own words). */
export type DocumentKind =
  | 'lab_report'
  | 'medicine_label'
  | 'discharge_letter'
  | 'clinic_slip'
  | 'handwritten_prescription'
  | 'insurance_letter'
  | 'insurance_policy'
  | 'insurance_claim'
  | 'device_screen'
  | 'pill_photo'
  | 'pharmacy_receipt'
  | 'other'
  | 'not_health'
  | 'unknown'
  | 'unsupported_file_type';

export type DocumentSource = 'portal' | 'email' | 'share';

export type FieldState = 'proposed' | 'confirmed' | 'corrected' | 'rejected';

/** The result's own printed reference range (`ReviewFieldOut.range`'s own doc) — never our judgement, only ever what the paper prints. */
export interface FieldRange {
  low: number | null;
  high: number | null;
  text: string | null;
}

export interface ReviewField {
  fieldId: string;
  position: number;
  subject: string;
  attribute: string;
  value: unknown;
  unit: string | null;
  confidence: number;
  needsConfirm: boolean;
  unreadable: boolean;
  /** The uncertain-field prompt line(s), in the reader's own words — never technical. */
  prompt: string[] | null;
  page: number | null;
  range: FieldRange | null;
  /** The words printed on the paper for this line — the web client's own fallback label ahead of a generic name. */
  labelOnPaper: string | null;
  /** The authoritative marker of where this field stands — never re-derived client-side. */
  state: FieldState;
  correctedValue: unknown;
  correctedByPersonId: string | null;
  factId: string | null;
}

/**
 * One choice on a clarifying question (spec W2): `label` is built by the
 * backend from confirmed record data — never free text off an
 * unconfirmed page. `value` is opaque: send it back unread on the next
 * turn (`AskIn.value` / a field's own `decision`).
 */
export interface ClarifyOption {
  label: string;
  value: string;
}

/**
 * The one plain question a card is asking (D-2, D-4b) — raw, structured
 * data. The screen builds the sentence in the reader's own language; the
 * backend only ever names a field's subject/kind, never composes prose.
 *
 * For `kind === 'whose_paper'`: `mismatched` names which of
 * name/patient_id/birth_year/sex disagreed — a closed set of field
 * names, **never the paper's own printed value** (the independent
 * safety review's fix: a card must never render whatever an unconfirmed
 * page's own name field says as if it were Nura's own words).
 */
export interface ReviewClarify {
  kind: string;
  mismatched: string[];
  existingCardId: string | null;
  existingAddedOn: string | null;
}

export interface ReviewCard {
  cardId: string;
  profileId: string;
  artifactId: string;
  documentKind: DocumentKind;
  documentDate: string | null;
  askedAs: DocumentKind | null;
  source: DocumentSource | null;
  /** Plain-words notices about the page itself (blurry, wrong side up, …) — never a technical code. */
  notice: string[] | null;
  highRiskClass: string | null;
  createdAt: string;
  confirmedAt: string | null;
  confirmedByPersonId: string | null;
  fields: ReviewField[];
  clarify: ReviewClarify | null;
  discarded: boolean;
  duplicateOfAddedOn: string | null;
}

export type FieldDecision = 'confirmed' | 'corrected' | 'rejected';

export interface FieldDecisionIn {
  fieldId: string;
  decision: FieldDecision;
  correctedValue?: unknown;
}

export interface ConfirmCardIn {
  decisions: FieldDecisionIn[];
  confirmationId: string;
  episodeId?: string | null;
}
