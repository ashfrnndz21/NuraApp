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

/** Recall over his own record, with citations (E03-05, `POST /profiles/{id}/ask`). Voice
 *  answers in the lines of one thing; text in up to five. */
export type AskMode = "voice" | "text";

export interface AnswerLineOut {
  /** One line the backend made from a template and the values it cites. */
  text: string;
  /** What the line rests on, by kind (`fact`, `event`, `artifact`, `appointment`, `provider`,
   *  `medication_line`, `attachment`, `summary_item`) and id; a cite of a consult recording
   *  carries the stretch of it the line is about, in seconds (E03-05). */
  cites: { kind: string; id: string; start_s?: number | null; end_s?: number | null }[];
  /** What "Hear what Dr Tan said" plays, when the line is about a recorded visit. */
  clip?: ClipOut | null;
}

/** The stretch of a consult recording a line plays on a tap (E03-05). */
export interface ClipOut {
  artifact_id: string;
  start_s: number;
  end_s: number;
  doctor: string;
}

export interface AnswerOut {
  question_artifact_id: string;
  mode: AskMode;
  language: string;
  answered: boolean;
  lines: AnswerLineOut[];
  /** What is said when the record does not answer, or the question would change treatment. */
  honest: string[];
  /** The recall surface's boundary lines: always last. */
  boundary: string[];
  /** The whole answer as he hears it, the boundary last. */
  spoken: string[];
  /** Parts of the record this key does not reach, so not read. */
  withheld: string[];
}

/** What a person did with a card (`POST /profiles/{id}/feed/{item}/engagement`). "Not for
 *  me" is `dismissed`: for the owner it holds that kind of card back for the rest of his day. */
export type EngagementEvent = "seen" | "heard" | "tapped" | "dismissed" | "shared";

export interface EngagementOut {
  engagement_id: string;
  item_id: string;
  event: EngagementEvent;
  channel: string;
  at: string;
}

/** The kinds of health card the family thread carries by reference (E12's `CardKind`),
 *  rendered at read time from the State they name — never words copied into the thread. */
export type ThreadCardKind = "reading" | "taken" | "visit" | "task";

export interface ThreadEntryOut {
  message_id: string;
  author_person_id: string;
  posted_at: string;
  text: string | null;
  card_kind: ThreadCardKind | null;
  state_id: string | null;
  task_id: string | null;
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
  /** Each dimension as the snapshot keeps it, or null where the key does not cover it. The
   *  client reads one thing here: his large-text setting (`functional.facts.vision`). */
  dimensions?: Record<string, { facts?: Record<string, Record<string, { value?: unknown }>> } | null>;
}

/** The emergency card (E13-01, `GET /profiles/{id}/emergency-card`): the data a stranger needs
 *  and the backend's verified lines that say it in his language. The phone keeps it (E00-08). */
export interface EmergencyCardOut {
  card_id: string;
  profile_id: string;
  state_id: string;
  rendered_at: string;
  name: string;
  language: string;
  spoken_language: string;
  age_band: string | null;
  conditions: { code: string; words: string; fact_id: string }[];
  medicines: {
    line_id: string;
    generic: string;
    brand: string | null;
    strength: string;
    form: string;
    plain_name: string;
    amount: string;
    when: string;
    high_risk: boolean;
    high_risk_class: string | null;
  }[];
  allergies: { code: string; words: string; fact_id: string }[];
  blood_type: string | null;
  high_risk: string[];
  contacts: { person_id: string; name: string; phone_e164: string | null; role: string }[];
  clinic: { provider_id: string; name: string; kind: string; phone_e164: string | null } | null;
  last_reading_at: string | null;
  /** The ambulance, by region: 995 in Singapore, 999 in Malaysia. */
  emergency_number: string;
  lines: { id: string; text: string }[];
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

/** A visit on the spine (`GET /profiles/{id}/appointments`: the ones still to come). */
export interface AppointmentOut {
  appointment_id: string;
  provider_id: string;
  scheduled_at: string;
  status: string;
  purpose: string;
}

/** One line of the logistics card (E05-03): its part, and the words as printed and spoken. */
export interface LogisticsLineOut {
  section: "when" | "place" | "note" | "driver" | "bring" | string;
  key: string;
  text: string;
  spoken: string;
}

/** The logistics card for one visit, composed by the backend from the record and State. The
 *  chief's note is hers, as she wrote it, under `label` ("Mei's note"). */
export interface LogisticsOut {
  appointment_id: string;
  provider_id: string;
  doctor: string;
  language: string;
  scheduled_at: string;
  state_id: string;
  place: string | null;
  note: { note_id: string; label: string; text: string; by_person_id: string; by_name: string; written_at: string } | null;
  driver: {
    status: "assigned" | "suggested" | "nobody" | "withheld";
    person_id: string | null;
    name: string | null;
    task_id: string | null;
    needs_yes: boolean;
    can_say_yes: boolean;
  };
  lines: LogisticsLineOut[];
  spoken: string[];
  withheld: string[];
}

/** What the Start button shows and speaks first (E16-02), handed back only once the gate
 *  (the RECORDING consent in force) has passed. */
export interface NoticeOut {
  appointment_id: string;
  doctor: string;
  language: string;
  spoken: string[];
  printed: string[];
  when_no: string[];
  consent_id: string;
}

export interface SegmentOut {
  segment_id: string;
  position: number;
  speaker: "patient" | "doctor" | "family" | "unknown";
  start_s: number;
  end_s: number;
  char_start: number;
  char_end: number;
}

export interface RecordingOut {
  recording_id: string;
  appointment_id: string;
  artifact_id: string;
  transcript_artifact_id: string | null;
  consent_id: string;
  duration_s: number;
  started_at: string;
  notice_language: string;
  doctor_named: boolean;
  heard: boolean;
  heard_confidence: number | null;
  recorded_by_person_id: string;
  segments: SegmentOut[];
}

export interface SummaryItemOut {
  item_id: string;
  position: number;
  kind: string;
  text: string;
  payload: Record<string, unknown>;
  confidence: number;
  state: string;
  /** Where in the recording this was said (E02-05); null when the notes were typed. */
  clip_start_s: number | null;
  clip_end_s: number | null;
}

/** The post-visit card (E05-05): the lines for him, the boundary last, the items behind them. */
export interface VisitSummaryOut {
  summary_id: string;
  appointment_id: string;
  artifact_id: string;
  language: string;
  red_flag: boolean;
  state_id: string;
  lines: string[];
  spoken: string[];
  boundary: string | null;
  items: SummaryItemOut[];
  created_at: string;
  recording_artifact_id: string | null;
}

/** What one upload kept, and the card it ended in, or why there is none yet. */
export interface ConsultOut {
  recording: RecordingOut;
  summary: VisitSummaryOut | null;
  summary_refused: string | null;
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

// --- E01: onboarding — #117's contract (branch E01-biography-profile, "Client contract") --
//
// #117 is merged; these are the shapes its routes answer with.

/** One word of the cloud (`GET /onboarding/conditions`): its code, his name for it, how large
 *  it sits, the words that appear once it is tapped, and whether the cloud shows it first. A
 *  word can appear under two picked words (a kidney number under pressure and sugar). */
export interface ConditionOut {
  code: string;
  name: string;
  weight: number;
  related: string[];
  top: boolean;
  /** Not modelled by E01 yet (its open question): the clinic's word, shown in brackets. */
  term?: string | null;
  /** Not modelled by E01 yet: a follow-up question and its options. */
  ask?: { question: string; options: { id: string; text: string }[] } | null;
}

export interface ConditionsOut {
  language: string;
  version: number;
  top: string[];
  conditions: ConditionOut[];
}

export type Density = "detailed" | "simple";

/** The settings screen, whole (`PUT /profiles/{id}/settings` replaces it). The words he
 *  tapped go here, as `conditions`. */
export interface SettingsIn {
  language: string;
  conditions: string[];
  density: Density;
  large_text: boolean;
  high_contrast: boolean;
  voice_on: boolean;
  big_targets: boolean;
  one_thing_per_screen: boolean;
  read_back: boolean;
  repeat_prompts: boolean;
  preferred_name: string | null;
  doctor_name: string | null;
  /** "07:30" on his wall clock. */
  breakfast_time: string | null;
  /** The decade he was born in, by its first year: 1950. */
  birth_decade: number | null;
}

/** The settings as the caller's key reads them; `withheld` names what it does not open. */
export interface SettingsOut extends Omit<SettingsIn, "conditions" | "doctor_name" | "birth_decade"> {
  settings_id: string | null;
  profile_id: string;
  conditions: string[] | null;
  doctor_name: string | null;
  birth_decade: number | null;
  set_by_person_id: string | null;
  set_at: string | null;
  withheld: string[];
}

/** The words of the step he is at, in his language. */
export interface ScriptOut {
  headline: string;
  lines: string[];
}

export type PaperKind = "discharge_letter" | "lab_result" | "medicine" | "clinic_card" | "insurance_card" | "other";

export interface PaperOut {
  paper_id: string;
  position: number;
  paper: PaperKind;
  artifact_id: string;
  card_id: string;
  document_kind: string;
  confirmed: boolean;
}

/** A paper joined to the sitting, and the review card it was read into. */
export interface PaperAddedOut {
  paper: PaperOut;
  card: ReviewCardOut;
}

/** A read-back line: the confirmed fact it reads back (its own source), the words, and his
 *  answer once given. E01 renders these from facts, not from State, so there is no State id. */
export interface ReadBackLineOut {
  fact_id: string;
  line: string;
  answer: "yes" | "no" | null;
  dispute_fact_id: string | null;
}

/** A question the papers raised: the gap it would fill, one whole line, Keep or Not this one,
 *  the State it was rendered from and its source line — and, once kept and handed over, the
 *  visit (appointment) whose list it went onto (E05). */
export interface QuestionOut {
  question_id: string;
  line: string;
  kept: boolean | null;
  state_id: string | null;
  source: string | null;
  handed_over_to: string | null;
}

export type BiographyStep = "about_you" | "papers" | "read_back" | "questions" | "closed";

/** Where the sitting stands (`POST`/`GET /profiles/{id}/biography`): its step, the one call to
 *  make next, the step's words, its papers, the read-back and the questions. */
export interface BiographyOut {
  biography_id: string;
  profile_id: string;
  step: BiographyStep;
  next: string | null;
  language: string;
  opened_at: string;
  opened_by_person_id: string;
  read_back_at: string | null;
  closed_at: string | null;
  prompt: ScriptOut;
  papers: PaperOut[];
  open_cards: number;
  read_back: ReadBackLineOut[];
  questions: QuestionOut[];
  /** After a "no" on the read-back: who looks at the paper again. */
  after_no: string | null;
  /** How many more questions wait for later. */
  more: string | null;
}

export interface SummaryOut {
  papers: number;
  facts: number;
  conditions: number;
  medicines: number;
  disputes: number;
  questions: number;
  prompts: number;
  first_prompt_at: string | null;
  lines: string[];
}

export type PromptCapture = "photo" | "pdf" | "tap" | "invite";

/** One day's prompt of the first week: the gap it fills, when it is due, how it is filled,
 *  and its words. E01 carries no State id or source line on a prompt; shown when present. */
export interface PromptOut {
  prompt: string;
  day: number;
  tier: number;
  capture: PromptCapture;
  /** The cloud word the gap is about, in his language (a name, not a code), or null. */
  word: string | null;
  deferred: number;
  due_at: string;
  due_local: string;
  status: "pending" | "done" | "skipped";
  done_at: string | null;
  done_by_fact_id: string | null;
  skipped_at: string | null;
  headline: string | null;
  line: string | null;
  action: string | null;
  state_id?: string;
  source?: string;
}

export interface PlanOut {
  plan_id: string;
  profile_id: string;
  biography_id: string | null;
  created_at: string;
  first_day: string;
  breakfast_time: string;
  timezone: string;
  stopped: boolean;
  stopped_because: string[];
  prompts: PromptOut[];
  due: PromptOut[];
}

/** The close of a sitting: where it stands, the summary in his words, and the first week. */
export interface ClosedOut {
  biography: BiographyOut;
  summary: SummaryOut;
  plan: PlanOut;
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
