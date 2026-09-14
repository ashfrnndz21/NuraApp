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
