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
  count: CountOut | null;
  doctor_question: string[];
  taken_label: string | null;
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
}

export interface AuditOut {
  entry_id: string;
  at: string;
  action: "read" | "write" | "share";
  scope: string;
  target: string;
  outcome: "allowed" | "refused";
  refused_because: string | null;
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
