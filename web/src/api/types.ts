/** The API's answers, as the backend's pydantic schemas name them
 *  (`backend/app/channels/api/schemas.py`). Only the fields the client reads are typed. */

export type Region = "SG" | "MY";
export type Posture = "stable" | "watch" | "act";
export type Standing = "owner" | "holder" | "steward" | "claimant" | "none";

export interface SessionOut {
  token: string;
  person_id: string;
  region: Region;
}

export interface MeOut {
  person_id: string;
  display_name: string;
  language: string;
  region: Region;
  email: string | null;
  profile_id: string | null;
}

export interface ProfileOut {
  profile_id: string;
  display_name: string;
  language: string;
  region: Region;
  role: string | null;
  scopes: string[];
  standing: Standing;
  /** The key the caller holds on it, or null for its owner. */
  key_id: string | null;
}

export interface ClaimableOut {
  profile_id: string;
  display_name: string;
  language: string;
  stewardship_id: string;
  steward_person_id: string;
  set_up_by: string;
  relationship: string | null;
  parts: string[];
  words_language: string;
  hold_wording_version: string;
  hold_words: string;
  sharing_wording_version: string;
  sharing_words: string;
}

export interface DoorsOut {
  own: ProfileOut | null;
  claimable: ClaimableOut[];
  invited: ProfileOut[];
  stewarding: ProfileOut[];
}

export interface WordingOut {
  purpose: string;
  version: string;
  language: string;
  region: Region;
  lines: string[];
}

export interface CountOut {
  remaining: number;
  unit: string;
  dispensed: number;
  taken: number;
  daily_amount: number | null;
  days_left: number | null;
  reorder_date: string | null;
  reorder_due: boolean;
  lead_time_days: number;
  basis: string;
  /** Patient sentences: "You have 28 tablets of your blood pressure tablet left." */
  lines: string[];
  reorder: string[];
}

export interface FlaggedOut {
  other_line_id: string;
  other_generic: string;
  severity: string;
  text_id: string;
  /** The interaction as a question for the doctor, both medicines in his words. */
  question: string[];
}

export interface LineOut {
  line_id: string;
  /** His word for it, in the language asked for: "your blood pressure tablet". */
  name: string;
  generic: string;
  brand: string | null;
  strength: string;
  form: string;
  high_risk: boolean;
  dose: { amount: number; unit: string; frequency: string; anchors: string[] };
  prescriber: string | null;
  status: string;
  started_at: string;
  count: CountOut | null;
  flags: FlaggedOut[];
  doctor_question: string[];
  taken_label: string | null;
  /** One of today's doses is in its window and not tapped / has passed its window untapped. */
  due_now: boolean;
  missed: boolean;
  /** The backend's source line: where the line came from and on which day, in his words. */
  source: string;
}

/** One dose card at one moment of his day (`GET /profiles/{id}/medicines/today`). */
export interface SlotOut {
  line_id: string;
  generic: string;
  anchor: string;
  /** The whole sentence: "Take 1 tablet of your blood pressure tablet with breakfast." */
  card: string;
  taken: boolean;
  taken_label: string;
  /** The backend's word on the moment: the client shows a dose only while `due_now`. */
  due_now: boolean;
  missed: boolean;
  /** The story's own missed-dose lines, filled only when `missed`. */
  if_forgotten: string[];
  /** The backend's source line for the card. */
  source: string;
}

/** One card of the feed (`GET /profiles/{id}/feed`), as the backend rendered it from a State. */
export interface FeedItemOut {
  item_id: string;
  type: string;
  /** flag, now, today, gate, story, learning — the backend's order, never re-ranked here. */
  supply: string;
  status: string;
  rendered_from_state: string;
  language: string;
  format: string;
  headline: string;
  body: string[];
  /** The spoken twin, line by line. */
  voice: string[];
  /** Why this card is here: `plain` is the sentence he reads under it. */
  why: { plain?: string; kind?: string } & Record<string, unknown>;
  priority: number;
  caps_class: string;
  scope: string;
  deliver_to: string;
  autoplay: boolean;
  source_id: string | null;
  cite: Record<string, unknown> | null;
  /** The boundary an inferring card is shown under (E16-01), lines joined by newlines; the
   *  same words its body and voice end on. Null on a card that shows the record back. */
  boundary: string | null;
  day: string;
  created_at: string;
  expires_at: string;
}

export interface FeedPageOut {
  audience: string;
  items: FeedItemOut[];
  cursor: string | null;
  next_cursor: string | null;
  quiet: boolean;
  held_by_caps: Record<string, number>;
}

export interface TakenOut {
  dose_taken_id: string;
  line_id: string;
  event_id: string;
  anchor: string | null;
  amount: number;
  taken_at: string;
  by_person_id: string;
}

export interface StateOut {
  state_id: string;
  profile_id: string;
  sequence: number;
  computed_at: string;
  posture: Posture;
  stale: boolean | null;
  stale_after: string | null;
  /** The line the posture is shown under (E16-01), one idea per line, joined by newlines. */
  boundary: string;
}

export interface ProudOut {
  days: number;
  as_of: string;
}

export interface KeyOut {
  key_id: string;
  holder_person_id: string;
  role: string;
  scopes: string[];
  expires_at: string | null;
  revoked_at: string | null;
  holder_display_name: string | null;
}

export interface ConfirmationOut {
  confirmation_id: string;
  subject: string;
  expires_at: string;
}

export interface ReadingOut {
  event_id: string;
  fact_id: string;
  taken_at: string;
}

/** How a refusal leaves the backend: the class name, and the scope for an OutOfScope. */
export interface RefusalBody {
  refusal: string;
  scope?: string;
  drug_class?: string;
}

// --- E02: a photo in, a review card out ------------------------------------------------

export type FieldState = "proposed" | "confirmed" | "corrected" | "rejected";

export interface ReviewFieldOut {
  field_id: string;
  position: number;
  subject: string;
  attribute: string;
  value: unknown;
  unit: string | null;
  confidence: number;
  /** Below the backend's threshold: the dotted underline, "please check this one". */
  needs_confirm: boolean;
  /** Nura saw this line and could not read it: `value` is null and `prompt` asks for it. */
  unreadable: boolean;
  /** The backend's whole lines shown beside a line nobody has typed yet (E02-02). */
  prompt: string[] | null;
  /** For a PDF of several pages, the page the line was read on. */
  page: number | null;
  state: FieldState;
  corrected_value: unknown | null;
  fact_id: string | null;
}

export type DocumentKind =
  | "lab_report"
  | "medicine_label"
  | "discharge_letter"
  | "clinic_slip"
  | "handwritten_prescription"
  | "insurance_letter"
  | "device_screen"
  | "not_health"
  | "unknown";

/** Where an imported PDF came from, in the backend's words (E02-03). */
export type DocumentSource = "portal" | "email" | "share";

export interface ReviewCardOut {
  card_id: string;
  profile_id: string;
  artifact_id: string;
  document_kind: DocumentKind;
  document_date: string | null;
  /** What he said a PDF was, and where it came from (E02-03). */
  asked_as: DocumentKind | null;
  source: DocumentSource | null;
  /** The backend's whole lines where the page is not what it was offered as, or not a
   *  health paper at all (then the card has no fields). */
  notice: string[] | null;
  high_risk_class: string | null;
  created_at: string;
  confirmed_at: string | null;
  fields: ReviewFieldOut[];
}

export interface DecisionIn {
  field_id: string;
  decision: "confirmed" | "corrected" | "rejected";
  corrected_value?: unknown;
}

export interface FactOut {
  fact_id: string;
  subject: string;
  attribute: string;
  value: unknown;
  unit: string | null;
}

export interface ReviewConfirmedOut {
  card: ReviewCardOut;
  facts: FactOut[];
}

// --- E01: onboarding — the shapes the web client codes against ---------------------------
//
// The backend half (branch E01-biography-profile) is being built beside this client. Until
// it lands these routes are answered by `src/api/mock/` when `VITE_API_MOCK=1`; the shapes
// here are the contract the mock keeps and the real client must match at merge.

/** One word of the cloud (`GET /onboarding/conditions?language=`). The plain word is what he
 *  reads; the medical term is in brackets on tap; the weight is how common it is. A word
 *  with a `parent` appears only once the parent is picked; `related` are the words that
 *  gain weight when this one is picked. */
export interface ConditionWordOut {
  id: string;
  word: string;
  term: string | null;
  weight: 1 | 2 | 3;
  parent: string | null;
  related: string[];
  ask: { question: string; options: { id: string; text: string }[] } | null;
}

export interface ConditionsOut {
  language: string;
  version: string;
  words: ConditionWordOut[];
}

/** `GET/PUT /profiles/{id}/settings` — E01-03. Every yes/no is a plain fact about how he
 *  reads, hears and holds the phone; the density and the voice follow at once. */
export interface SettingsOut {
  profile_id: string;
  preferred_name: string | null;
  language: string;
  birth_decade: number | null;
  doctor: string | null;
  /** "07:30", the anchor every morning reminder ties to. */
  breakfast_time: string | null;
  sight: boolean;
  hearing: boolean;
  hands: boolean;
  cognitive: boolean;
  updated_at: string | null;
}

export type SettingsIn = Omit<SettingsOut, "profile_id" | "updated_at">;

/** One line of the read-back: the backend's whole sentence, with the State it was rendered
 *  under and where it came from. The client never composes one. */
export interface ReadBackLineOut {
  line_id: string;
  text: string;
  answer: "yes" | "no" | null;
  state_id: string;
  source: string;
}

/** The assistant's next prompt in the records step: whole lines to show and speak, and
 *  what it is asking for. `kind: "done"` is the closing line. */
export interface PromptOut {
  prompt_id: string;
  kind: "paper" | "done";
  lines: string[];
  state_id: string;
  source: string;
}

/** A paper the biography has taken in, and the whole lines the backend learned from it. */
export interface PaperOut {
  paper_id: string;
  card_id: string;
  artifact_id: string;
  document_kind: ReviewCardOut["document_kind"];
  learned: string[];
  source: string;
}

/** A question the papers raised, as E01's sitting holds it: one whole line, spoken as
 *  written, with Keep or Not this one. E01's shape carries no State id and no source line;
 *  the card shows them when the backend sends them. */
export interface QuestionOut {
  question_id: string;
  line: string;
  kept: boolean | null;
  state_id?: string;
  source?: string;
}

export interface BiographyOut {
  biography_id: string;
  profile_id: string;
  language: string;
  opened_at: string;
  closed_at: string | null;
  words: string[];
  answers: Record<string, string>;
  read_back: ReadBackLineOut[];
  next_prompt: PromptOut | null;
  papers: PaperOut[];
  questions: QuestionOut[];
}

export interface BiographyIn {
  language: string;
  words: string[];
  answers: Record<string, string>;
}

/** One gap card (`GET /profiles/{id}/plan`, docs/gaps-and-unlocks.md §1): three whole lines
 *  from the backend, the one action, the day it is for, and its State and source. */
export interface PlanCardOut {
  gap_id: string;
  day: string;
  tier: 1 | 2 | 3;
  missing: string;
  unlock: string;
  action: string;
  /** What "do it now" opens: the camera, the follow-up question of `word`, the invite
   *  (E12: a sharing consent, then a key), or nothing. `word` and `"invite"` are proposed
   *  to E01; the mock answers with them. */
  capture: "photo" | "tap" | "invite" | "none";
  word?: string | null;
  state_id: string;
  source: string;
  deferred: number;
}

export interface PlanOut {
  profile_id: string;
  state_id: string;
  cards: PlanCardOut[];
}

// --- E12: letting one person in (sharing consent, then a key), from the Ready screen ---

export type Part = "medicines" | "visits" | "readings" | "records";

export interface SharingIn {
  holder_phone_e164: string;
  /** The name the words use for the person, as he calls them (`HolderNeedsAName` without it). */
  holder_display_name: string;
  scopes: Part[];
  relationship: string | null;
  language: string;
}

/** The words he agrees to, rendered by the backend for this person and these parts before
 *  he says yes (`POST /profiles/{id}/consents/sharing/preview`), by the same function the
 *  consent keeps them with. The client never composes them. */
export interface SharingPreviewOut {
  wording_version: string;
  language: string;
  lines: string[];
}

export interface ConsentOut {
  consent_id: string;
  holder_person_id: string | null;
  scopes: string[] | null;
  text_version: string;
  wording_text: string;
}


// --- E05: a question kept for the next visit ---------------------------------------------

/** One visit still to come (`GET /profiles/{id}/appointments`, soonest first). */
export interface AppointmentOut {
  appointment_id: string;
  provider_id: string;
  scheduled_at: string;
  status: string;
  purpose: string;
}

/** A question on a visit's list (`POST /appointments/{id}/questions`), with its source. */
export interface VisitQuestionOut {
  question_id: string;
  appointment_id: string;
  text: string;
  source: string;
  state_id: string;
}
