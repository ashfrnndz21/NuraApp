import { api, apiBlob, apiText, apiUpload } from "./client";
import type {
  AppointmentOut,
  ConsultOut,
  LogisticsOut,
  NoticeOut,
  VisitSummaryOut,
  AnswerOut,
  AskMode,
  BiographyOut,
  ClaimableOut,
  ClosedOut,
  ConditionsOut,
  ConfirmationOut,
  ConsentOut,
  DecisionIn,
  DocumentSource,
  DoorsOut,
  EmergencyCardOut,
  EngagementEvent,
  EngagementOut,
  FeedPageOut,
  KeyOut,
  LineOut,
  MeOut,
  PaperAddedOut,
  PlanOut,
  ProfileOut,
  ProudOut,
  ReadingOut,
  ReviewCardOut,
  ReviewConfirmedOut,
  SessionOut,
  SettingsIn,
  SettingsOut,
  SharingIn,
  SharingPreviewOut,
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

/** His tap. `takenAt` is a tap the phone held while offline (E00-08): the moment he made it,
 *  which the backend writes once however often it is sent. */
export const taken = (token: string, profileId: string, lineId: string, anchor: string | null, takenAt?: string) =>
  api<TakenOut>(`/profiles/${profileId}/medicines/${lineId}/taken`, {
    method: "POST",
    token,
    body: takenAt ? { anchor, taken_at: takenAt } : { anchor },
  });

/** A word on the feeling strip (E17), as the phone held it while offline. */
export const feeling = (token: string, profileId: string, word: string, language: string) =>
  api<unknown>(`/profiles/${profileId}/feelings`, { method: "POST", token, body: { word, language } });

/** The emergency card, rendered now from State, in his language (E13-01). */
export const emergencyCard = (token: string, profileId: string, language: string) =>
  api<EmergencyCardOut>(`/profiles/${profileId}/emergency-card`, { token, query: { language } });

/** The same card as the backend's one printable page: self-contained, nothing fetched. */
export const emergencyCardPage = (token: string, profileId: string, language: string) =>
  apiText(`/profiles/${profileId}/emergency-card.html`, { token, query: { language } });

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
  api<VisitSummaryOut>(`/profiles/${profileId}/appointments/${appointmentId}/transcript`, {
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

// --- E02: a photo in, a review card out, facts on his yes (live on main) ------------------

/** The photo's bytes go up as base64 in JSON, the way `PhotoIn` asks; the answer is the
 *  review card. A PDF goes the same way until a documents route exists, and the backend's
 *  own refusal (`NotAPhoto`) is what he reads if it cannot take one. */
export const addPhoto = (token: string, profileId: string, data: string, content_type: string, captured_at: string) =>
  api<ReviewCardOut>(`/profiles/${profileId}/photos`, {
    method: "POST",
    token,
    body: { data, content_type, captured_at },
  });

export const mintReviewYes = (token: string, profileId: string, card_id: string, decisions: DecisionIn[]) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "review_card", card_id, decisions },
  });

export const confirmReviewCard = (
  token: string,
  profileId: string,
  cardId: string,
  decisions: DecisionIn[],
  confirmation_id: string,
) =>
  api<ReviewConfirmedOut>(`/profiles/${profileId}/review-cards/${cardId}/confirm`, {
    method: "POST",
    token,
    body: { decisions, confirmation_id },
  });

// --- E01: onboarding (#117) ---------------------------------------------------------------------

/** The word cloud: public, in his language. */
export const conditions = (token: string, language: string) =>
  api<ConditionsOut>("/onboarding/conditions", { token, query: { language } });

export const settings = (token: string, profileId: string) =>
  api<SettingsOut>(`/profiles/${profileId}/settings`, { token });

/** The settings screen, whole: a PUT replaces it, and the words he tapped go in as `conditions`. */
export const putSettings = (token: string, profileId: string, body: SettingsIn) =>
  api<SettingsOut>(`/profiles/${profileId}/settings`, { method: "PUT", token, body });

/** Open the sitting (no body). One already open is `BiographyAlreadyOpen` (409): read it instead. */
export const openBiography = (token: string, profileId: string) =>
  api<BiographyOut>(`/profiles/${profileId}/biography`, { method: "POST", token });

export const biography = (token: string, profileId: string, language: string) =>
  api<BiographyOut>(`/profiles/${profileId}/biography`, { token, query: { language } });

/** A card made through capture (`/photos`, `/imports`) joins the sitting. */
export const attachPaper = (token: string, profileId: string, card_id: string) =>
  api<PaperAddedOut>(`/profiles/${profileId}/biography/papers`, { method: "POST", token, body: { card_id } });

/** One read-back line a screen: the fact it reads back, and his yes or no. */
export const answerReadBack = (token: string, profileId: string, fact_id: string, answer: "yes" | "no") =>
  api<BiographyOut>(`/profiles/${profileId}/biography/read-back`, {
    method: "POST",
    token,
    body: { line_id: fact_id, answer },
  });

export const answerQuestion = (token: string, profileId: string, question_id: string, keep: boolean) =>
  api<BiographyOut>(`/profiles/${profileId}/biography/questions`, { method: "POST", token, body: { question_id, keep } });

/** Close the sitting: where it stands, the summary in his words and the first week come back. */
export const closeBiography = (token: string, profileId: string) =>
  api<ClosedOut>(`/profiles/${profileId}/biography/close`, { method: "POST", token });

export const plan = (token: string, profileId: string, language: string) =>
  api<PlanOut>(`/profiles/${profileId}/plan`, { token, query: { language } });

/** Later, on one prompt: the first sends it to the back of the week, the second retires it. */
export const laterOnPlan = (token: string, profileId: string, gap_id: string) =>
  api<PlanOut>(`/profiles/${profileId}/plan/later`, { method: "POST", token, body: { gap_id } });

/** A PDF to be read (E02-03), the same review card back. `source` is where it came from, in
 *  the backend's words; a file picked on the phone is sent as a share. */
export const addImport = (
  token: string,
  profileId: string,
  data: string,
  content_type: string,
  captured_at: string,
  source: DocumentSource,
) =>
  api<ReviewCardOut>(`/profiles/${profileId}/imports`, {
    method: "POST",
    token,
    body: { data, content_type, captured_at, source },
  });

// --- E12: letting one person in ------------------------------------------------------

/** The words for this person and these parts, exactly as the consent will keep them. */
export const previewSharing = (token: string, profileId: string, body: SharingIn) =>
  api<SharingPreviewOut>(`/profiles/${profileId}/consents/sharing/preview`, { method: "POST", token, body });

/** The owner's own yes to letting this person in, in the words he was shown (their version). */
export const letSomeoneIn = (token: string, profileId: string, body: SharingIn, wording_version: string) =>
  api<ConsentOut>(`/profiles/${profileId}/consents/sharing`, {
    method: "POST",
    token,
    body: { ...body, captured_via: "app", wording_version },
  });

/** The key that rests on that yes: a caregiver's, to the same parts and no wider. */
export const cutKey = (token: string, profileId: string, holder_phone_e164: string, scopes: SharingIn["scopes"]) =>
  api<KeyOut>(`/profiles/${profileId}/keys`, {
    method: "POST",
    token,
    body: { holder_phone_e164, role: "caregiver", scopes },
  });
