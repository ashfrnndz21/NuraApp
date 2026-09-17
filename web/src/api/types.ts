import type { Relationship } from "../strings/types";
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
  /** Who set it up is to him, in the words' language: "your daughter". */
  relationship_words?: string | null;
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
  /** His own graph, or one keyed to him, whose owner's closing stands (#143): ids, never opened. */
  closing?: string[];
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
  /** The reorder card's two buttons in his words, by action (E04-05); empty until the
   *  count is at the threshold: `ask_to_order`, `i_have_more`. */
  reorder_actions?: Record<string, string>;
}

export interface FlaggedOut {
  other_line_id: string;
  other_generic: string;
  severity: string;
  text_id: string;
  /** The interaction as a question for the doctor, both medicines in his words. */
  question: string[];
  /** What a pharmacist would check this pair against (E04-03). */
  source?: string;
  /** True while no pharmacist has checked this pair yet: `question` then asks him to check
   *  with a pharmacist too, rather than naming a severity or a mechanism (E04-03). Still
   *  shown, never silent. */
  awaiting_review?: boolean;
}

/** A prescription medicine, a supplement (a vitamin, a mineral or a Western-style herbal
 *  product), or a traditional remedy — TCM (E04-03). Screened for interactions the same way;
 *  never shown as though it were a prescription medicine. */
export type ProductKind = "prescription" | "supplement" | "tcm";

export interface LineOut {
  line_id: string;
  /** His word for it, in the language asked for: "your blood pressure tablet". */
  name: string;
  generic: string;
  brand: string | null;
  strength: string;
  form: string;
  high_risk: boolean;
  /** A prescription medicine, a supplement or a TCM remedy (E04-03). */
  product_kind?: ProductKind;
  /** How sure the licensed registry was that its match is this product (#206) — never
   *  below the floor a line had to clear to be written at all. Distinct from `confidence`
   *  below, which is the person's yes, not the register's own certainty. */
  registry_confidence?: number | null;
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
  /** The `medication` fact the line is the typed view of (a reorder card cites it). */
  fact_id?: string;
  /** How sure, as a number and in words (E04-01): a line written on a person's yes is
   *  `confirmed_by_person`. */
  confidence?: number;
  confidence_state?: "extracted" | "confirmed_by_person" | "disputed";
  /** The other active lines of the same medicine: two strengths in the cupboard. */
  duplicate_of?: string[];
  source_artifact_id?: string | null;
  change_kind?: string;
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
  /** For today's top three (E11-02): alert, reminder or insight. */
  category?: string | null;
  /** The watch that found this card, when a search made it (F1): what "Pause this watch" pauses. */
  search_job_id?: string | null;
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
  /** The question as it was kept; null when a red word in it took the red-flag path instead. */
  question_artifact_id: string | null;
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
  /** A red flag heard in the question: the red-flag path it took first, as the same word
   *  tapped on the feeling cloud would (the moment written, the flag raised, the family told).
   *  Null when the question carries none. */
  red_flag?: FeelingOut | null;
}

/** One real stage of an ask or a search, streamed the instant it finishes (docs/design-
 *  direction.md "Conversation, waiting and thinking"): which part of his record Nura just
 *  read, in his language, already in the caregiver's voice if this key is not his own — never
 *  invented, never held back, never named for a part this key's scope does not open. */
export interface AskStepEvent {
  type: "step";
  key: string;
  label: string;
  /** The bare noun for the collapsed "What Nura looked at: {name}, {name}" line. */
  name: string;
}

/** The stream's last event: the finished answer, exactly `POST /profiles/{id}/ask` returns. */
export interface AskAnswerEvent {
  type: "answer";
  answer: AnswerOut;
}

/** A refusal heard mid-stream — a scope the key does not hold, a malformed question — in the
 *  same shape `apiStream` turns into a thrown `Refused`, so a caller need not special-case it. */
export interface AskRefusalEvent {
  type: "refusal";
  refusal: string;
  status: number;
  scope?: string;
}

export type AskStreamEvent = AskStepEvent | AskAnswerEvent | AskRefusalEvent;

/** The feed's web/video search, streamed the same way (`POST /profiles/{id}/find/stream`):
 *  one step while the search runs, then the results `POST /profiles/{id}/find` would return. */
export interface FindStepEvent {
  type: "step";
  key: "searching";
  label: string;
}
export interface FindResultsEvent {
  type: "results";
  results: FindResultOut[];
}
export type FindStreamEvent = FindStepEvent | FindResultsEvent | AskRefusalEvent;

/** What a person did with a card (`POST /profiles/{id}/feed/{item}/engagement`). "Not for
 *  me" is `dismissed`: for the owner it holds that kind of card back for the rest of his day. */
export type EngagementEvent = "seen" | "heard" | "tapped" | "dismissed" | "shared" | "opened" | "played" | "replayed" | "asked_more";

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
  /** The posture as one word and one line, in the language asked for (D1: the chief's hero). */
  word?: string;
  line?: string;
  /** What raised the posture, as chips, each with its tone. */
  drivers?: StateDriverOut[];
  /** Each dimension as the snapshot keeps it, or null where the key does not cover it. The
   *  client reads one thing here: his large-text setting (`functional.facts.vision`). */
  dimensions?: Record<string, { facts?: Record<string, Record<string, { value?: unknown }>> } | null>;
}

export interface StateDriverOut {
  key: string;
  text: string;
  tone: string | null;
}

/** The one big number on his Today (`GET …/medicines/now`): null when nothing is left today. */
export interface NowOut {
  count: number | null;
  anchor: string | null;
  words: string | null;
}

/** One line of what changed, in his words, with the tone of its dot (null: no tone). */
export interface ChangeLineOut {
  section: string;
  key: string;
  text: string;
  tone?: string | null;
}

export interface ChangesOut {
  language: string;
  first_look: boolean;
  lines: ChangeLineOut[];
  waiting: ChangeLineOut[];
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
    has_plain_name: boolean;
    amount: string;
    when: string;
    high_risk: boolean;
    high_risk_class: string | null;
    high_risk_label: string | null;
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
  contact?: string;
  drug_class?: string;
}

/** A visit on the spine (`GET /profiles/{id}/appointments`: the ones still to come). */
export interface AppointmentOut {
  appointment_id: string;
  provider_id: string;
  scheduled_at: string;
  status: string;
  purpose: string;
  /** The doctor's or clinic's name as the family wrote it (the provider's); absent where the
   *  route does not read it. */
  doctor?: string | null;
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
  /** Where in the transcript it was heard, by character; null when there is none. */
  span?: { start: number; end: number } | null;
  /** Once the card is confirmed, what the item became. */
  memo_id?: string | null;
  appointment_id?: string | null;
  fact_id?: string | null;
  flag_id?: string | null;
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
  /** When his yes closed the card (E05-05); null while it waits for it. */
  confirmed_at?: string | null;
  recording_artifact_id: string | null;
}

/** What one upload kept, and the card it ended in, or why there is none yet. */
export interface ConsultOut {
  recording: RecordingOut;
  summary: VisitSummaryOut | null;
  summary_refused: string | null;
}

/** A visit's recording on its way in, in chunks (#129): what the server has of it. */
export interface UploadOut {
  upload_id: string;
  /** How many chunks the server has, in order: the number of the next one to send. */
  chunks: number;
  /** How many bytes they hold: where in the recording the next chunk starts. */
  received_bytes: number;
  doctor_said_yes: boolean;
  /** Whether it still takes chunks: false once put together, thrown away, or lapsed. */
  open: boolean;
  max_chunk_bytes: number;
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
  | "unknown"
  | "unsupported_file_type";

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
  /** When it holds from: a reading's moment. */
  valid_from: string;
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
  relationship: Relationship | null;
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
  /** What the agreement is for, by the backend's code (`share_with_family` lets one person in). */
  purpose?: string;
  person_id?: string;
  holder_person_id: string | null;
  scopes: string[] | null;
  text_version: string;
  language?: string;
  /** The words as he read them and agreed to, one idea per line. */
  wording_text: string;
  granted_at?: string;
  revoked_at?: string | null;
}

// --- W5: the Record (E03, E04, E09-01, E10-01, E02-04, E02-08, E12-09) -----------------------

/** One anchor of the spine: the last check-up, the last visit, the next visit, in his words. */
export interface AnchorOut {
  key: string;
  line: string;
  appointment_id: string | null;
  provider_id: string | null;
  at: string | null;
}

export interface ProviderOut {
  provider_id: string;
  name: string;
  kind: "doctor" | "clinic" | "hospital" | "pharmacy" | "lab" | "other" | string;
  region: Region;
  phone_e164: string | null;
  address: string | null;
}

export interface EpisodeOut {
  episode_id: string;
  kind: string;
  label: string;
  opened_at: string;
  closed_at: string | null;
}

export interface VisitOut {
  appointment_id: string;
  provider_id: string;
  scheduled_at: string;
  status: "planned" | "confirmed" | "attended" | "not_attended" | "cancelled" | string;
  purpose: string;
  episode_id: string | null;
}

/** An artefact by reference: what kind, when, how it came in. Never its content. */
export interface ArtifactRefOut {
  artifact_id: string;
  kind: "photo" | "pdf" | "voice" | "message" | "reading" | "screenshot" | "transcript" | string;
  content_type: string;
  captured_at: string;
  source_channel: string;
}

export interface EventRefOut {
  event_id: string;
  kind: string;
  occurred_at: string;
  label: string | null;
  artifact_id: string | null;
  episode_id: string | null;
  withheld: string[];
}

/** One entry on the timeline — a visit or an episode — and what hangs off it. */
export interface TimelineItemOut {
  kind: "appointment" | "episode" | string;
  id: string;
  at: string;
  appointment: VisitOut | null;
  provider: ProviderOut | null;
  episode: EpisodeOut | null;
  visits: string[];
  artifacts: ArtifactRefOut[];
  events: EventRefOut[];
  facts: FactOut[];
  notes: unknown[];
}

export interface TimelineOut {
  language: string;
  header: AnchorOut[];
  items: TimelineItemOut[];
  next_cursor: string | null;
  withheld: string[];
}

export interface EpisodeViewOut {
  episode: TimelineItemOut;
  visits: TimelineItemOut[];
  withheld: string[];
}

export interface ProviderSummaryOut {
  provider: ProviderOut;
  visits: number;
  last_visit: VisitOut | null;
  next_visit: VisitOut | null;
}

export interface PlaceNoteOut {
  note_id: string;
  provider_id: string;
  text: string;
  written_by_person_id: string;
  written_at: string;
}

export interface ProviderHistoryOut {
  provider: ProviderOut;
  visits: VisitOut[];
  papers: { artifact: ArtifactRefOut; kind: string; via: string; appointment_id: string | null; episode_id: string | null; fact_ids: string[] }[];
  medicines: { line_id: string; generic: string; strength: string; prescriber: string | null; fact_id: string; started_at: string }[];
  /** The owner's and his chief's notes about the place; empty for anyone else. */
  notes: PlaceNoteOut[];
  withheld: string[];
}

export interface ChangeLineOut {
  section: string;
  key: string;
  text: string;
  refs: Record<string, string[]>;
}

/** What changed since the reader last looked, and what is still waiting (E03-04). */
export interface ChangesOut {
  language: string;
  since: string | null;
  first_look: boolean;
  looked_at: string;
  lines: ChangeLineOut[];
  waiting: ChangeLineOut[];
  withheld: string[];
}

export interface RangeOut {
  lower: number | null;
  upper: number | null;
  unit: string;
  source: string;
  source_id: string;
  lab: string | null;
}

export interface TrendPointOut {
  fact_id: string;
  artifact_id: string | null;
  value: number;
  unit: string | null;
  on: string;
  lab: string | null;
  band: string;
  range: RangeOut | null;
  no_range_because: string | null;
}

/** One analyte over time (E09-01): results oldest first, each against its range; the lines
 *  he reads, ending on the boundary line (`boundary` is that line too). */
export interface TrendOut {
  analyte: string;
  unit: string;
  language: string;
  points: TrendPointOut[];
  direction: string;
  direction_since: string | null;
  lines: string[];
  boundary: string;
  doctor: string | null;
  card_id: string;
  state_id: string;
}

export interface RoutineMedicineOut {
  line_id: string;
  generic: string;
  strength: string;
  name: string;
  amount: number;
  unit: string;
  frequency: string;
}

export interface RoutineMomentOut {
  anchor: string;
  at: string;
  medicines: RoutineMedicineOut[];
  /** Null when the reader's key does not open the readings. */
  readings: string[] | null;
  walk: boolean;
}

/** The day (E10-01): his lines (one per moment) or her table, and the day as set. */
export interface RoutineOut {
  routine_id: string | null;
  set: boolean;
  anchors: Record<string, string>;
  reading_prompts: string[][] | null;
  walks: string[];
  morning_card_at: string;
  persona: "patient" | "caregiver";
  language: string;
  lines: string[];
  table: RoutineMomentOut[];
  withheld: string[];
}

export interface RoutineDayIn {
  anchors: Record<string, string>;
  reading_prompts: [string, string][];
  walks: string[];
  morning_card_at: string;
}

/** The story of one medicine (E04-06), in his language; `lines` is the voice script. */
export interface StoryOut {
  line_id: string;
  language: string;
  name: string;
  generic: string;
  strength: string;
  purpose: string[];
  how_to_take: string[];
  watch_out: string[];
  avoid: string[];
  if_forgotten: string[];
  boundary: string[];
  doctor_question: string[];
  lines: string[];
  /** The parts said as voice notes (E04-06), in order, each played from
   *  `…/medicines/{line}/story/voice?part=`. Absent from a backend that has none yet. */
  voice_parts?: string[];
}

/** What one label or pack said, as typed or as read off the photo (E04-03). */
export interface LabelIn {
  generic?: string | null;
  brand?: string | null;
  strength?: string | null;
  dose_text?: string | null;
  quantity?: number | null;
  prescriber?: string | null;
}

export type MedicineOutcome = "new_line" | "refill" | "dose_change" | "duplicate";

/** What a label would do to the list, before anyone says yes: screened for interactions. */
export interface MedicineDraftOut {
  outcome: MedicineOutcome;
  match: {
    registration_no: string;
    brand: string;
    generic: string;
    strength: string;
    form: string;
    drug_class: string;
    high_risk: boolean;
    product_kind: ProductKind;
    product_name: string;
    licence_status: string;
    active_ingredients: string[];
    confidence: number;
  };
  matched_line_id: string | null;
  flagged: FlaggedOut[];
  needs_label_photo: boolean;
  lead_time_days: number;
}

export interface ReconciledOut {
  outcome: MedicineOutcome;
  line_id: string;
  generic: string;
  strength: string;
  high_risk: boolean;
}

/** What he reads before his yes to "Ask the family to order." (E04-05): the one person the
 *  task will name, in his words. `already_asked` when the family was asked for this line
 *  today and the task is still open: the one line says so, and a yes answers with that task. */
export interface OrderPreviewOut {
  line_id: string;
  asked_person_id: string;
  already_asked: boolean;
  task_id: string | null;
  language: string;
  lines: string[];
}

/** What "Ask the family to order." did (E04-05), on his yes. */
export interface AskedOut {
  line_id: string;
  task_id: string;
  asked_person_id: string;
  told_person_ids: string[];
  language: string;
  lines: string[];
  already_asked: boolean;
}

/** What "I have more at home." wrote, and the count now (E04-05). */
export interface MoreOut {
  line_id: string;
  supply_id: string;
  fact_id: string;
  event_id: string;
  /** The photo of the box or the label the count rests on; a high-risk medicine's needs one. */
  artifact_id: string | null;
  quantity: number;
  count: CountOut | null;
}

// --- W7: the patient's day (E05-01, E05-02, E05-05, E13-02, E14-01, E17, E11-07, E21-03) -----

/** One line the backend wrote, with the template it came from. */
export interface IdLineOut {
  id: string;
  text: string;
}

/** One line of the pre-visit brief: its section (purpose, changed, questions, bring,
 *  boundary), the words as printed and as said. */
export interface BriefLineOut {
  section: string;
  key: string;
  text: string;
  spoken: string;
  sources: string[];
}

/** The pre-visit brief (E05-01, `GET …/appointments/{appt}/brief`), ending on its boundary. */
export interface BriefOut {
  brief_id: string;
  appointment_id: string;
  language: string;
  state_id: string;
  built_at: string;
  lines: BriefLineOut[];
  boundary: string | null;
}

/** One question for the visit (E05-02), with its source. */
export interface VisitQuestionOut {
  question_id: string;
  appointment_id: string;
  text: string;
  language: string;
  source: string;
  source_kind: string | null;
  source_ids: string[];
  priority: number;
  added_by_person_id: string | null;
  supersedes_id: string | null;
  removed: boolean;
  state_id: string;
  created_at: string;
}

/** The questions, and his one card: the first three, a reassurance, the boundary. */
export interface VisitQuestionsOut {
  questions: VisitQuestionOut[];
  card: string[];
  spoken_card: string[];
}

/** Add (`text`), edit (`text`, `question_id`) or remove (`question_id`, `remove`) one. */
export interface QuestionChange {
  text?: string;
  question_id?: string;
  remove?: boolean;
}

export interface ItemDecision {
  item_id: string;
  decision: "confirmed" | "rejected";
}

export interface MemoOut {
  memo_id: string;
  appointment_id: string | null;
  kind: string;
  source: string;
  text: string;
  language: string;
  state_id: string;
  created_at: string;
}

/** What his yes to a post-visit card wrote (E05-05): never a medicine. */
export interface SummaryConfirmedOut {
  summary: VisitSummaryOut;
  memos: MemoOut[];
  appointments: AppointmentOut[];
  facts: FactOut[];
  flag_ids: string[];
}

/** The memo card (`GET /profiles/{id}/memos`): the lines, ending on the boundary. */
export interface MemoCardOut {
  memos: MemoOut[];
  card: string[];
  spoken_card: string[];
}

/** What he said: typed words, or a voice note as base64 with its content type. */
export interface Said {
  words?: string;
  audio?: string;
  content_type?: string;
}

/** The what-to-do-now card (E13-02): `lines` in the order he reads them, never re-ordered. */
export interface WhatToDoOut {
  card_id: string | null;
  state_id: string | null;
  kind: "red_flag" | "missed_dose" | "rest" | string;
  posture: Posture | null;
  language: string;
  lines: IdLineOut[];
  artifact_id: string | null;
  event_id: string | null;
  fact_id: string | null;
  heard: boolean;
  by_voice: boolean;
  transcript_confidence: number;
  red_flags: string[];
  suppressed: string[];
  symptoms: string[];
  flag_id: string | null;
  notified_person_ids: string[];
  check_in_at: string | null;
  missed_medicine: string | null;
}

/** The two cards the phone keeps for when it cannot reach Nura (W7): fixed, verified lines. */
export interface OfflineCardsOut {
  language: string;
  emergency_number: string;
  red_flag: IdLineOut[];
  unknown: IdLineOut[];
}

export interface SymptomEntryOut {
  fact_id: string;
  event_id: string | null;
  artifact_id: string | null;
  at: string;
  symptoms: string[];
  red_flags: string[];
  severity: number | null;
  severity_words: string | null;
  duration: string | null;
  by_voice: boolean;
  heard: boolean;
  confidence: number;
  lines: IdLineOut[];
}

/** A symptom written down (E14-01): the entry in plain words, and a red flag if one was said. */
export interface SymptomLoggedOut {
  entry: SymptomEntryOut;
  posture: Posture | null;
  flag_id: string | null;
  notified_person_ids: string[];
  suppressed: string[];
  /** A red flag in what he said: the button's urgent card, in its order (null otherwise). */
  card?: IdLineOut[] | null;
}

/** The log, oldest first, every entry's lines in order (or the one line for an empty log). */
export interface SymptomLogOut {
  since: string;
  entries: SymptomEntryOut[];
  lines: IdLineOut[];
}

/** One word on the feeling cloud. `reasons` are for the audit, never for his screen. */
export interface CloudWordOut {
  word: string;
  label: string;
  weight: number;
  red: boolean;
  reasons: Record<string, unknown>[];
}

/** The feeling cloud on Today (E17-01): whether it shows, the question, the words. */
export interface CloudOut {
  state_id: string | null;
  language: string;
  show: boolean;
  because: string;
  prompt: string[];
  words: CloudWordOut[];
}

export interface FeelingQuestionOut {
  follow_up: string;
  words: string;
  /** `red`: this answer makes the word a red flag, so a failure to send it shows the red card. */
  answers: { answer: string; label: string; red?: boolean }[];
}

/** A note kept for the visit (E17-02): the headline, what to tell, who does the next thing,
 *  and the boundary it ends on. */
export interface FeelingNoteOut {
  note_id: string;
  tap_id: string;
  word: string;
  answer: string;
  language: string;
  headline: string;
  lines: string[];
  then: string;
  voice: string[];
  boundary: string;
  outcome: string;
  appointment_id: string | null;
  rendered_from_state: string;
  created_at: string;
}

/** What the red-flag path wrote, when it ran: the flag, who was told, the ladder, the card. */
export interface RedPathOut {
  red_flag: boolean;
  flag_id: string | null;
  told: string[];
  suppressed_because: string | null;
  escalation_id: string | null;
  opens: string | null;
  card: WhatToDoOut | null;
}

/** A tap on the cloud: a red word's path, or the one question back. */
export interface FeelingOut extends RedPathOut {
  event_id: string;
  word: string;
  tap_id: string;
  language: string;
  question: FeelingQuestionOut | null;
  lines: string[];
}

/** His one answer: a note, or — a yes that made the word red — the red-flag path. */
export interface AnsweredOut extends RedPathOut {
  tap_id: string;
  answer: string;
  lines: string[];
  note: FeelingNoteOut | null;
  note_withheld_because: string | null;
}

export interface NudgeDraftOut {
  kind: string;
  lines: string[];
  voice: string[];
  language: string;
  why: string;
  cap_class: string;
  day: string;
  send_after: string;
  expires_at: string;
  state_id: string;
  priority: number;
  dedupe_key: string;
}

/** The day's plan (E17-03): at most what goes, what is held and why. */
export interface NudgePlanOut {
  day: string;
  drafts: NudgeDraftOut[];
  held: { kind: string; because: string; priority: number | null }[];
  none_because: string | null;
}

export interface NudgeOut {
  nudge_id: string;
  kind: string;
  day: string;
  lines: string[];
  why: string;
  cap_class: string;
  send_after: string;
  expires_at: string;
  rendered_from_state: string;
  handed_over_at: string;
}

export interface HandedOverOut {
  plan: NudgePlanOut;
  nudge: NudgeOut;
}

/** A nudge handed over for the day (`GET /profiles/{id}/nudges`), and what the reader did. */
export interface DayNudgeOut extends NudgeOut {
  voice: string[];
  responses: string[];
}

export interface DayNudgesOut {
  day: string;
  nudges: DayNudgeOut[];
  withheld: number;
}

export type NudgeAnswer = "seen" | "accepted" | "dismissed";

/** The Me page (`GET /profiles/{id}/me-summary`): the number that only goes up, in his words. */
export interface MeSummaryOut {
  name: string;
  language: string;
  proud_days: number;
  as_of: string;
  lines: string[];
}

/** A stretch of a consult recording one line of a feed card was said in (E21-03): the
 *  memo card's `cite.clips`. `line` is the card's own line, its caption. */
export interface CardClipOut {
  line: string;
  artifact_id: string;
  start_s: number;
  end_s: number;
  doctor: string;
}

/** `GET /api/deployment`: the region this backend serves, and whether it is a demo (ADR 0008). */
export interface DeploymentOut {
  region: "SG" | "MY";
  demo: boolean;
  /** A declared dev run: the only place a laptop's `nura-dev-` staff token is taken. */
  dev?: boolean;
  /** The Web Push key the home-screen app subscribes with; null when there is no Web Push. */
  push_key?: string | null;
}

/** One event from the phone's queue (E11-08, `POST …/feed/events`). `seconds` only on a play
 *  or a replay: how much of a clip or voice note played. Nothing measures time in the feed. */
export interface QueuedEventIn {
  client_id: string;
  item_id: string;
  event: EngagementEvent;
  at: string;
  channel?: "app";
  seconds?: number | null;
}

export interface EventsOut {
  written: string[];
  skipped: { client_id: string; because: string }[];
}

/** One card of "Sent to Pa this week": the card and its status. No count of anything. */
export interface SentOut {
  item: FeedItemOut;
}

export type JobKind = "explainer" | "safety" | "local" | "food" | "provider" | "worth_knowing" | "seasonal";

/** One watch of "Watching for Pa": what for (the backend's words), its sources, how often. */
export interface SearchJobOut {
  job_id: string;
  kind: JobKind;
  terms: string[];
  source_ids: string[];
  cadence: string;
  reason: Record<string, unknown>;
  status: string;
  results: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  label: string;
  sources: string[];
}

/** His area, coarse (E09-07): a town from the list or a postcode's first digits. */
export interface AreaOut {
  area: string | null;
  districts: string[];
  may_set: boolean;
}

export type FindWhere = "web" | "videos" | "providers";

/** One thing the ask bar's Web, Videos or Providers filter found: the backend's words. */
export interface FindResultOut {
  title: string;
  publisher: string | null;
  url: string | null;
  published_at: string | null;
  lines: string[];
  boundary: string | null;
  media: string | null;
  provider_id: string | null;
  next_visit_at: string | null;
}

export interface FindOut {
  where: string;
  results: FindResultOut[];
}
