import { api, apiBlob, apiUpload } from "./client";
import type {
  AppointmentOut,
  ConsultOut,
  LogisticsOut,
  NoticeOut,
  SummaryOut,
  ClaimableOut,
  ConfirmationOut,
  DoorsOut,
  AnswerOut,
  AskMode,
  EngagementEvent,
  EngagementOut,
  FeedPageOut,
  KeyOut,
  LineOut,
  MeOut,
  ProfileOut,
  ProudOut,
  ReadingOut,
  SessionOut,
  SlotOut,
  StateOut,
  TakenOut,
  ThreadCardKind,
  ThreadEntryOut,
  WordingOut,
} from "./types";

/** Every route the client uses, one function each, in the backend's own names. */

export const startPhone = (phone_e164: string, display_name: string | null, language: string) =>
  api<{ expires_in_seconds: number }>("/auth/phone/start", {
    method: "POST",
    body: { phone_e164, display_name: display_name || null, language },
  });

export const verifyPhone = (phone_e164: string, code: string) =>
  api<SessionOut>("/auth/phone/verify", { method: "POST", body: { phone_e164, code } });

export const startEmail = (email: string, display_name: string | null, language: string) =>
  api<{ expires_in_seconds: number }>("/auth/email/start", {
    method: "POST",
    body: { email, display_name: display_name || null, language },
  });

export const verifyEmail = (email: string, token: string) =>
  api<SessionOut>("/auth/email/verify", { method: "POST", body: { email, token } });

export const signOut = (token: string) => api<void>("/auth/logout", { method: "POST", token });

export const me = (token: string) => api<MeOut>("/me", { token });

export const doors = (token: string, language: string) =>
  api<DoorsOut>("/doors", { token, query: { language } });

export const wording = (language: string) =>
  api<WordingOut>("/consent/wording", { query: { purpose: "hold_health_record", language } });

export const openOwnProfile = (
  token: string,
  args: { version: string; language: string; display_name: string | null },
) =>
  api<ProfileOut>("/profiles/mine", {
    method: "POST",
    token,
    body: {
      consent: { wording_version: args.version, language: args.language, captured_via: "app" },
      display_name: args.display_name || null,
      language: args.language,
    },
  });

export const setUpForSomeone = (
  token: string,
  args: {
    patient_phone_e164: string;
    display_name: string;
    language: string;
    version: string;
    relationship: string | null;
  },
) =>
  api<ProfileOut>("/profiles/for-someone", {
    method: "POST",
    token,
    body: {
      patient_phone_e164: args.patient_phone_e164,
      display_name: args.display_name,
      language: args.language,
      consent: { wording_version: args.version, language: args.language, captured_via: "app" },
      basis: "patient_asked",
      relationship: args.relationship || null,
    },
  });

export const claimable = (token: string, language: string) =>
  api<ClaimableOut[]>("/profiles/mine/claimable", { token, query: { language } });

export const mintClaim = (token: string, profileId: string, language: string) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "claim", language },
  });

export const claim = (token: string, profileId: string, confirmation_id: string, language: string) =>
  api<ProfileOut>(`/profiles/${profileId}/claim`, {
    method: "POST",
    token,
    body: { confirmation_id, language, captured_via: "app" },
  });

export const profile = (token: string, profileId: string) =>
  api<ProfileOut>(`/profiles/${profileId}`, { token });

export const medicines = (token: string, profileId: string, language: string) =>
  api<LineOut[]>(`/profiles/${profileId}/medicines`, { token, query: { language } });

export const dosesToday = (token: string, profileId: string, language: string) =>
  api<SlotOut[]>(`/profiles/${profileId}/medicines/today`, { token, query: { language } });

export const taken = (token: string, profileId: string, lineId: string, anchor: string | null) =>
  api<TakenOut>(`/profiles/${profileId}/medicines/${lineId}/taken`, {
    method: "POST",
    token,
    body: { anchor },
  });

export const state = (token: string, profileId: string) =>
  api<StateOut>(`/profiles/${profileId}/state`, { token });

/** The proud number, counted by the backend from the DOSE_TAKEN events in one audited read. */
export const proud = (token: string, profileId: string) =>
  api<ProudOut>(`/profiles/${profileId}/proud`, { token });

/** The first page of the feed: today's cards, rendered by the backend from a State. */
export const feed = (token: string, profileId: string) =>
  api<FeedPageOut>(`/profiles/${profileId}/feed`, { token });

/** One page of the feed (E21): no cursor makes today's cards and answers the first page; a
 *  cursor answers the page it names, as of when it was minted — the same cursor, the same page. */
export const feedPage = (token: string, profileId: string, cursor?: string) =>
  api<FeedPageOut>(`/profiles/${profileId}/feed`, { token, query: { cursor } });

/** The last first page rendered for this person, as it was: the page kept for offline. */
export const feedCached = (token: string, profileId: string) =>
  api<FeedPageOut>(`/profiles/${profileId}/feed/cached`, { token });

/** What he did with a card: heard, tapped, shared, or "Not for me" (`dismissed`). */
export const engage = (token: string, profileId: string, itemId: string, event: EngagementEvent) =>
  api<EngagementOut>(`/profiles/${profileId}/feed/${itemId}/engagement`, {
    method: "POST",
    token,
    body: { event, channel: "app" },
  });

/** A card into the family thread, by reference (E12): the thread renders it from the State. */
export const shareCard = (token: string, profileId: string, card_kind: ThreadCardKind) =>
  api<ThreadEntryOut>(`/profiles/${profileId}/thread`, { method: "POST", token, body: { card_kind } });

/** A question about his own record (E03): his words go to the backend as they are; the answer
 *  comes back as cited lines, the honest line when nothing answers, and the boundary last. */
export const ask = (token: string, profileId: string, question: string, mode: AskMode, language: string) =>
  api<AnswerOut>(`/profiles/${profileId}/ask`, { method: "POST", token, body: { question, mode, language } });

/** A card's pre-rendered voice (E11), when the backend has the route. */
export const feedVoice = (token: string, profileId: string, itemId: string, language: string) =>
  apiBlob(`/profiles/${profileId}/feed/${itemId}/voice`, { token, query: { language } });

/** The keys on the profile with their holders' names: the owner reads whom to call. */
export const keys = (token: string, profileId: string) =>
  api<KeyOut[]>(`/profiles/${profileId}/keys`, { token });

export const addReading = (token: string, profileId: string, systolic: number, diastolic: number) =>
  api<ReadingOut>(`/profiles/${profileId}/readings`, {
    method: "POST",
    token,
    body: { systolic, diastolic },
  });

// --- the visit day (E05-03, E05-04, E02-05, E03-05) ---------------------------------------

/** The visits still to come, soonest first. */
export const appointments = (token: string, profileId: string) =>
  api<AppointmentOut[]>(`/profiles/${profileId}/appointments`, { token });

/** The logistics card: when, where, the chief's note, who drives him, what to bring. */
export const logistics = (token: string, profileId: string, appointmentId: string) =>
  api<LogisticsOut>(`/profiles/${profileId}/appointments/${appointmentId}/logistics`, { token });

/** The chief's yes to one person driving him to one visit (subject `drive`). */
export const mintDrive = (token: string, profileId: string, appointmentId: string, personId: string) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "drive", appointment_id: appointmentId, person_id: personId },
  });

/** Spend that yes: the family task "drive Pa to Dr Tan". */
export const assignDriver = (token: string, profileId: string, appointmentId: string, personId: string, confirmationId: string) =>
  api<unknown>(`/profiles/${profileId}/appointments/${appointmentId}/driver`, {
    method: "POST",
    token,
    body: { person_id: personId, confirmation_id: confirmationId },
  });

/** What the Start button asks first: the gate, then the notice. A refusal means nothing is
 *  said in the room and the microphone is not asked for. */
export const recordingNotice = (token: string, profileId: string, appointmentId: string) =>
  api<NoticeOut>(`/profiles/${profileId}/appointments/${appointmentId}/recording/notice`, { token });

/** Today's words for Nura listening at the visit, for the owner to read before his yes. */
export const recordingWording = (language: string) =>
  api<WordingOut>("/consent/wording", { query: { purpose: "recording", language } });

/** The owner's yes to those words, exactly as shown. */
export const agreeToRecording = (token: string, profileId: string, version: string, language: string) =>
  api<unknown>(`/profiles/${profileId}/consents/recording`, {
    method: "POST",
    token,
    body: { wording_version: version, language, captured_via: "app" },
  });

/** The recording, once, on Stop: the recorder's own bytes as the body. */
export const uploadRecording = (token: string, profileId: string, appointmentId: string, audio: Blob, durationS: number, startedAt: string) =>
  apiUpload<ConsultOut>(`/profiles/${profileId}/appointments/${appointmentId}/recording`, audio, audio.type || "audio/webm", {
    token,
    query: { duration_s: durationS.toFixed(1), started_at: startedAt },
  });

/** The notes by hand, when the doctor says no: E05's typed transcript, read into the card. */
export const writeNotes = (token: string, profileId: string, appointmentId: string, text: string) =>
  api<SummaryOut>(`/profiles/${profileId}/appointments/${appointmentId}/transcript`, {
    method: "POST",
    token,
    body: { data: base64OfText(text) },
  });

/** A stretch of a consult recording: the whole recording, to play from `start` to `end`. */
export const clip = (token: string, profileId: string, artifactId: string, start: number, end: number) =>
  apiBlob(`/profiles/${profileId}/artifacts/${artifactId}/clip`, { token, query: { start: String(start), end: String(end) } });

function base64OfText(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
