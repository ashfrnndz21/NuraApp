import { api, apiText } from "./client";
import type { AppointmentOut, ConfirmationOut, ConsentOut, KeyOut, WordingOut } from "./types";
import type {
  AcceptedOut,
  ConnectorOut,
  DeliveryOut,
  DeliverySettingsIn,
  DeliverySettingsOut,
  DocumentOut,
  DocumentTag,
  LadderOut,
  OpenLadderOut,
  ReachOut,
  DigestOut,
  GrantOut,
  KeyRole,
  KeyWindow,
  NudgeMetricsOut,
  OnDutyOut,
  PrivacyOut,
  ProposalOut,
  PushCompose,
  PushOut,
  PushPreviewOut,
  PushWhen,
  RolePresetOut,
  RosterSlotOut,
  ScanOut,
  Scope,
  TaskOut,
  ThreadEntryOut,
  TrailDayOut,
  WithdrawalOut,
  WithdrawnOut,
} from "./familyTypes";

/** Every route the Family screens use, one function each, in the backend's own names. */

const yes = (token: string, profileId: string, body: Record<string, unknown>) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, { method: "POST", token, body });

// --- E12-01: roles and keys -----------------------------------------------------------------

/** The six roles with their default parts and window, said for `name`, in `language`. */
export const roles = (token: string, language: string, name: string) =>
  api<RolePresetOut[]>("/family/roles", { token, query: { language, name } });

/** Every live key as a grant, in his words. The owner's and his chief's. */
export const grants = (token: string, profileId: string, language: string) =>
  api<GrantOut[]>(`/profiles/${profileId}/grants`, { token, query: { language } });

/** A key for one person: a role, the parts, a window. It rests on the owner's own agreement to
 *  let that person in; without it the backend refuses (`ConsentWithheld`). */
export const makeKey = (token: string, profileId: string, body: { holder_phone_e164: string; role: KeyRole; scopes: Scope[]; window: KeyWindow }) =>
  api<KeyOut>(`/profiles/${profileId}/keys`, { method: "POST", token, body });

/** The yes to narrowing one key to these parts and this window; wider is refused here already. */
export const mintKeyChange = (token: string, profileId: string, key_id: string, scopes: Scope[], window: KeyWindow | null) =>
  yes(token, profileId, { subject: "key_change", key_id, scopes, ...(window ? { window } : {}) });

export const narrowKey = (token: string, profileId: string, keyId: string, scopes: Scope[], window: KeyWindow | null, confirmation_id: string) =>
  api<KeyOut>(`/profiles/${profileId}/keys/${keyId}`, { method: "PUT", token, body: { scopes, ...(window ? { window } : {}), confirmation_id } });

export const closeKey = (token: string, profileId: string, keyId: string) =>
  api<KeyOut>(`/profiles/${profileId}/keys/${keyId}`, { method: "DELETE", token });

// --- E00-07, E12-04: his trail and only me ----------------------------------------------------

export const trail = (token: string, profileId: string, language: string) =>
  api<TrailDayOut[]>(`/profiles/${profileId}/trail`, { token, query: { language } });

export const privacy = (token: string, profileId: string) => api<PrivacyOut[]>(`/profiles/${profileId}/privacy`, { token });

export const mintOnlyMe = (token: string, profileId: string, scope: Scope, only_me: boolean) =>
  yes(token, profileId, { subject: "only_me", scope, only_me });

export const markOnlyMe = (token: string, profileId: string, scope: Scope, confirmation_id: string) =>
  api<PrivacyOut>(`/profiles/${profileId}/privacy`, { method: "POST", token, body: { scope, confirmation_id } });

export const liftOnlyMe = (token: string, profileId: string, scope: Scope, confirmation_id: string) =>
  api<PrivacyOut>(`/profiles/${profileId}/privacy/${scope}/lift`, { method: "POST", token, body: { confirmation_id } });

// --- E00-02: what he agreed to, stopping one, and the record to keep ------------------------------

export const consents = (token: string, profileId: string) => api<ConsentOut[]>(`/profiles/${profileId}/consents`, { token });

/** What stopping this agreement will do, in his words: the confirm step. */
export const withdrawal = (token: string, profileId: string, consentId: string, language: string) =>
  api<WithdrawalOut>(`/profiles/${profileId}/consents/${consentId}/withdrawal`, { token, query: { language } });

export const withdraw = (token: string, profileId: string, consentId: string, language: string) =>
  api<WithdrawnOut>(`/profiles/${profileId}/consents/${consentId}/withdraw`, { method: "POST", token, body: { captured_via: "app", language } });

/** Keeping his papers is stopped by closing his account (#143): his yes to exactly the lines
 *  the withdrawal showed, then the closing itself. */
export const closeAccount = async (token: string, profileId: string, language: string) => {
  const said = await yes(token, profileId, { subject: "close_account", language });
  return api<{ closing: boolean; delete_after: string | null }>(`/profiles/${profileId}/closure`, {
    method: "POST",
    token,
    body: { confirmation_id: said.confirmation_id, language },
  });
};

/** The printable record, as the backend renders it: one self-contained page. */
export const consentRecord = (token: string, profileId: string) => apiText(`/profiles/${profileId}/consents/record.html`, { token });

// --- E12-02: the family thread and the digest ---------------------------------------------------

export const digest = (token: string, profileId: string, since: string, language: string) =>
  api<DigestOut>(`/profiles/${profileId}/thread/digest`, { token, query: { since, language } });

export const postMessage = (token: string, profileId: string, text: string) =>
  api<ThreadEntryOut>(`/profiles/${profileId}/thread`, { method: "POST", token, body: { text } });

// --- E12-03: the roster and the tasks ---------------------------------------------------------------

export const roster = (token: string, profileId: string) => api<RosterSlotOut[]>(`/profiles/${profileId}/roster`, { token });

export const onDuty = (token: string, profileId: string) => api<OnDutyOut[]>(`/profiles/${profileId}/roster/on-duty`, { token });

export const addSlot = (
  token: string,
  profileId: string,
  body: { person_id: string; role: KeyRole; weekdays: number[]; from_time: string; to_time: string },
) => api<RosterSlotOut>(`/profiles/${profileId}/roster`, { method: "POST", token, body });

export const endSlot = (token: string, profileId: string, slotId: string) =>
  api<RosterSlotOut>(`/profiles/${profileId}/roster/${slotId}`, { method: "DELETE", token });

/** Every task (owner and chief), or with `mine` the ones that name the caller. */
export const tasks = (token: string, profileId: string, mine: boolean) =>
  api<TaskOut[]>(`/profiles/${profileId}/tasks`, { token, query: { mine: mine ? "true" : undefined } });

export const addTask = (token: string, profileId: string, body: { what: string; assigned_person_id: string; due_at: string | null }) =>
  api<TaskOut>(`/profiles/${profileId}/tasks`, { method: "POST", token, body });

export const mintTaskDone = (token: string, profileId: string, task_id: string) => yes(token, profileId, { subject: "task_done", task_id });

export const taskDone = (token: string, profileId: string, taskId: string, confirmation_id: string) =>
  api<TaskOut>(`/profiles/${profileId}/tasks/${taskId}/done`, { method: "POST", token, body: { confirmation_id } });

export const appointments = (token: string, profileId: string) => api<AppointmentOut[]>(`/profiles/${profileId}/appointments`, { token });

// --- E12-06: messages to him ------------------------------------------------------------------

/** Exactly what he will see. */
export const previewPush = (token: string, profileId: string, compose: PushCompose) =>
  api<PushPreviewOut>(`/profiles/${profileId}/pushes/preview`, { method: "POST", token, body: compose });

/** The yes binds to the lines as previewed, then, there, until. */
export const mintPush = (token: string, profileId: string, compose: PushCompose, when: PushWhen) =>
  yes(token, profileId, { subject: "push", ...compose, ...when });

export const schedulePush = (token: string, profileId: string, compose: PushCompose, when: PushWhen, confirmation_id: string) =>
  api<PushOut>(`/profiles/${profileId}/pushes`, { method: "POST", token, body: { ...compose, ...when, confirmation_id } });

export const pushes = (token: string, profileId: string) => api<PushOut[]>(`/profiles/${profileId}/pushes`, { token });

// --- E17-05: the week in numbers ----------------------------------------------------------------

export const nudgeMetrics = (token: string, profileId: string, weeks = 4) =>
  api<NudgeMetricsOut>(`/profiles/${profileId}/nudge-metrics`, { token, query: { weeks: String(weeks) } });

// --- E18-02: a calendar file, read once, and its proposals -------------------------------------

export const calendarWording = (language: string) => api<WordingOut>("/consent/wording", { query: { purpose: "calendar", language } });

/** Connect, on the calendar agreement in force; the owner may agree to it in the same step. */
export const connectCalendar = (token: string, profileId: string, consent?: { wording_version: string; language: string }) =>
  api<ConnectorOut>(`/profiles/${profileId}/connectors/calendar`, {
    method: "POST",
    token,
    body: consent ? { consent: { ...consent, captured_via: "app" } } : {},
  });

export const scanCalendar = (token: string, profileId: string, connectorId: string, ics: string, language: string) =>
  api<ScanOut>(`/profiles/${profileId}/connectors/${connectorId}/scan`, { method: "POST", token, body: { ics }, query: { language } });

export const proposals = (token: string, profileId: string, language: string) =>
  api<ProposalOut[]>(`/profiles/${profileId}/proposals`, { token, query: { language } });

export const mintProposal = (token: string, profileId: string, proposal_id: string) =>
  yes(token, profileId, { subject: "appointment_proposal", proposal_id });

export const acceptProposal = (token: string, profileId: string, proposalId: string, confirmation_id: string, language: string) =>
  api<AcceptedOut>(`/profiles/${profileId}/proposals/${proposalId}/accept`, { method: "POST", token, body: { confirmation_id }, query: { language } });

export const dismissProposal = (token: string, profileId: string, proposalId: string, language: string) =>
  api<ProposalOut>(`/profiles/${profileId}/proposals/${proposalId}/dismiss`, { method: "POST", token, query: { language } });

// --- E00-05, E11-05, E11-06: what was sent, when and how, and "I'm on it" --------------------------

/** Every attempt to reach someone about him, newest first, with the rule that fired. */
export const deliveries = (token: string, profileId: string) => api<DeliveryOut[]>(`/profiles/${profileId}/deliveries`, { token });

export const deliverySettings = (token: string, profileId: string) => api<DeliverySettingsOut>(`/profiles/${profileId}/delivery-settings`, { token });

export const changeDeliverySettings = (token: string, profileId: string, body: DeliverySettingsIn) =>
  api<DeliverySettingsOut>(`/profiles/${profileId}/delivery-settings`, { method: "PUT", token, body });

/** The red flags still climbing that reached the caller, with the lines beside "I'm on it". */
export const ladders = (token: string, profileId: string, language: string) =>
  api<OpenLadderOut[]>(`/profiles/${profileId}/ladders`, { token, query: { language } });

export const acknowledge = (token: string, profileId: string, ladderId: string, language: string) =>
  api<LadderOut>(`/profiles/${profileId}/ladders/${ladderId}/acknowledge`, { method: "POST", token, query: { language } });

/** Who Nura cannot message on WhatsApp, in the backend's words (owner and chief; #163). */
export const reach = (token: string, profileId: string, language: string) => api<ReachOut[]>(`/profiles/${profileId}/reach`, { token, query: { language } });

// --- E12-09: the papers behind the family list ----------------------------------------------------

export const documents = (token: string, profileId: string) => api<DocumentOut[]>(`/profiles/${profileId}/documents`, { token });

export const addDocument = (token: string, profileId: string, body: { data: string; content_type: string; captured_at: string; tag: DocumentTag }) =>
  api<DocumentOut[]>(`/profiles/${profileId}/documents`, { method: "POST", token, body });
