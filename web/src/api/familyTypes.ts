/** The shapes the Family screens read (E12, E00-02, E00-07, E17-05, E18-02), in the backend's
 *  own names. Every `lines` field is the backend's words; the client shows them as they are. */

import type { ConsentOut } from "./types";

export type KeyRole = "chief" | "caregiver" | "viewer" | "helper" | "emergency" | "clinic";
export type KeyWindow = "always" | "one_day" | "thirty_days" | "seventy_two_hours";
/** Every part of the record a key can be cut to (`Scope`, less `profile`, which every key holds). */
export type Scope = "medicines" | "visits" | "readings" | "records" | "notes" | "money" | "family" | "emergency" | "ask" | "send";

export interface RolePresetOut {
  role: KeyRole;
  scopes: string[];
  window: KeyWindow;
  lines: string[];
}

export interface GrantOut {
  key_id: string;
  holder_person_id: string;
  holder_name: string;
  role: KeyRole;
  scopes: string[];
  window: KeyWindow | null;
  granted_at: string;
  expires_at: string | null;
  lines: string[];
}

export interface TrailLineOut {
  at: string;
  who: string;
  sentences: string[];
  outcome: string;
}

export interface TrailDayOut {
  day: string;
  day_words: string;
  lines: TrailLineOut[];
}

export interface PrivacyOut {
  privacy_id: string;
  scope: Scope;
  marked_at: string;
  lifted_at: string | null;
}

export interface DigestEntryOut {
  kind: string;
  at: string;
  lines: string[];
  /** A family member's own words, never Nura's to rewrite. */
  text: string | null;
  message_id: string | null;
}

export interface DigestOut {
  language: string;
  since: string;
  headline: string;
  entries: DigestEntryOut[];
  on_duty: string[];
  /** Every line Nura wrote, in order: the headline, each entry's lines, then the closing. */
  lines: string[];
}

export interface ThreadEntryOut {
  message_id: string;
  author_person_id: string;
  posted_at: string;
  text: string | null;
  card_kind: string | null;
}

export interface RosterSlotOut {
  slot_id: string;
  person_id: string;
  role: KeyRole;
  weekdays: number[] | null;
  starts_on: string | null;
  ends_on: string | null;
  from_time: string;
  to_time: string;
  ended_at: string | null;
}

export interface OnDutyOut {
  slot_id: string;
  person_id: string;
  role: KeyRole;
}

export interface TaskOut {
  task_id: string;
  /** The chief's words for the task. */
  what: string;
  assigned_person_id: string;
  due_at: string | null;
  created_by_person_id: string;
  created_at: string;
  done_at: string | null;
  done_by_person_id: string | null;
  appointment_id: string | null;
  errand: string | null;
}

export interface PushCompose {
  template_id?: string;
  slots?: Record<string, string>;
  memo_lines?: string[];
  language?: string;
}

export interface PushWhen {
  send_at: string;
  channel: "app" | "whatsapp";
  expires_at: string;
}

export interface PushPreviewOut {
  language: string;
  template_id: string | null;
  lines: string[];
  notes: string[];
}

export interface PushOut {
  push_id: string;
  language: string;
  template_id: string | null;
  lines: string[];
  send_at: string;
  channel: "app" | "whatsapp";
  expires_at: string;
  /** The delivery log's word (E11): sent once it reached him, not_sent when its end passed first. */
  state: "scheduled" | "sent" | "not_sent";
  sent_at: string | null;
}

export interface KindCountsOut {
  handed_over: number;
  accepted: number;
  dismissed: number;
  seen: number;
  ignored: number;
  acceptance: number | null;
}

export interface WeekOut {
  week: string;
  starts_on: string;
  taps: number;
  fine_today: number;
  fine_share: number | null;
  nudges: Record<string, KindCountsOut>;
}

export interface NudgeMetricsOut {
  weeks: WeekOut[];
  ignored_streaks: Record<string, number>;
  resting: string[];
  as_of: string;
}

export interface ConnectorOut {
  connector_id: string;
  kind: string;
  source: string;
  consent_id: string;
}

export interface ProposalOut {
  proposal_id: string;
  connector_id: string;
  title: string;
  starts_at: string;
  provider_name: string;
  status: "proposed" | "accepted" | "dismissed";
  appointment_id: string | null;
  /** What he reads about it, in his language; empty once dismissed. */
  lines: string[];
}

export interface ScanOut {
  read: number;
  proposed: ProposalOut[];
  dropped: number;
  already: number;
}

export interface AcceptedOut {
  proposal: ProposalOut;
  appointment_id: string;
  scheduled_at: string;
  appointment_status: string;
}

export interface WithdrawalOut {
  consent_id: string;
  purpose: string;
  lines: string[];
}

export interface WithdrawnOut {
  consent_id: string;
  purpose: string;
  withdrawn: ConsentOut[];
  lines: string[];
}
