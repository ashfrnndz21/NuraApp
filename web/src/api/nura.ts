import { api, apiBlob, apiBytes, apiStream, apiText, apiUpload, sendAndForget } from "./client";
import type {
  AnswerOut,
  AnsweredOut,
  AppointmentOut,
  AreaOut,
  AskedOut,
  AskMode,
  AskRefusalEvent,
  AskStreamEvent,
  BiographyOut,
  BriefOut,
  ChangesOut,
  ClaimableOut,
  ClosedOut,
  CloudOut,
  ConditionsOut,
  ConfirmationOut,
  ConsentOut,
  ConsultOut,
  DayNudgesOut,
  DecisionIn,
  DeploymentOut,
  DocumentSource,
  DoorsOut,
  EmergencyCardOut,
  EngagementEvent,
  EngagementOut,
  EpisodeViewOut,
  EventsOut,
  FactOut,
  FeedItemOut,
  FeedPageOut,
  FeelingOut,
  FindOut,
  FindStreamEvent,
  FindWhere,
  FoodCatalogItemOut,
  FoodEntryOut,
  FoodLogIn,
  HandedOverOut,
  HealthOverviewOut,
  ItemDecision,
  JobKind,
  KeyOut,
  LabelIn,
  LedgerOut,
  LineOut,
  LogisticsOut,
  MeOut,
  MeSummaryOut,
  MedicineDraftOut,
  MemoCardOut,
  MetricEntryOut,
  MetricKind,
  MetricLogIn,
  MoreOut,
  NoticeOut,
  NowOut,
  NudgeAnswer,
  NudgePlanOut,
  OfflineCardsOut,
  OrderPreviewOut,
  PaperAddedOut,
  PlaceNoteOut,
  PlanOut,
  PolicyOut,
  ProfileOut,
  ProudOut,
  ProviderHistoryOut,
  ProviderSummaryOut,
  QuestionChange,
  QueuedEventIn,
  ReadingOut,
  ReconciledOut,
  ReviewCardOut,
  ReviewConfirmedOut,
  RoutineDayIn,
  RoutineOut,
  Said,
  SearchJobOut,
  SentOut,
  SessionOut,
  SettingsIn,
  SettingsOut,
  SharingIn,
  SharingPreviewOut,
  SignalFamily,
  SignalsOut,
  SlotOut,
  StateOut,
  StoryOut,
  SummaryConfirmedOut,
  SymptomLogOut,
  SymptomLoggedOut,
  TakenOut,
  ThreadCardKind,
  ThreadEntryOut,
  TimelineOut,
  TrendOut,
  UploadOut,
  VisitQuestionOut,
  VisitQuestionsOut,
  VisitSummaryOut,
  WhatToDoOut,
  WordingOut,
} from "./types";

/** Every route the client uses, one function each, in the backend's own names. */

/** Which region this is, and whether it is a demo (ADR 0008). No token: it is not anyone's data. */
export const deployment = () => api<DeploymentOut>("/deployment");

/** This phone gets reminders about this profile (Web Push, ADR 0001). */
export const subscribePush = (token: string, profileId: string, subscription: PushSubscriptionJSON) =>
  api<{ subscription_id: string }>(`/profiles/${profileId}/push-subscriptions`, {
    method: "POST",
    token,
    body: { endpoint: subscription.endpoint, keys: { p256dh: subscription.keys?.p256dh, auth: subscription.keys?.auth } },
  });

/** This phone stops getting them. */
export const forgetPush = (token: string, profileId: string, endpoint: string) =>
  api<void>(`/profiles/${profileId}/push-subscriptions`, { method: "DELETE", token, body: { endpoint } });

export const startPhone = (phone_e164: string, display_name: string | null, language: string) =>
  api<{ expires_in_seconds: number }>("/auth/phone/start", {
    method: "POST",
    body: { phone_e164, display_name: display_name || null, language },
  });

export const verifyPhone = (phone_e164: string, code: string) =>
  api<SessionOut>("/auth/phone/verify", { method: "POST", body: { phone_e164, code } });

/** "Try it as Pa"/"Try it as Mei" on the Welcome screen, demo/dev only (`GET /deployment`):
 *  signs in as the number `app.demo_seed` seeded, without the phone number and the code a
 *  real sign-in asks for. Answers 404 wherever the deployment has not seeded them. */
export const quickSignIn = (as: "pa" | "mei") =>
  api<SessionOut>("/dev/quick-signin", { method: "POST", body: { as } });

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

/** The State, its word, line and drivers in `language` (the profile's own when not given). */
export const state = (token: string, profileId: string, language?: string) =>
  api<StateOut>(`/profiles/${profileId}/state`, { token, query: { language } });

/** The one big number on his Today and what it counts (D1, `GET …/medicines/now`). */
export const medicinesNow = (token: string, profileId: string, language: string) =>
  api<NowOut>(`/profiles/${profileId}/medicines/now`, { token, query: { language } });

/** The facts that hold now about one subject — his blood pressures, for the chief's sparkline. */
export const facts = (token: string, profileId: string, subject: string) =>
  api<FactOut[]>(`/profiles/${profileId}/facts`, { token, query: { subject } });

/** The Health Overview (design-direction.md, the Health tab): the ring — doses taken this
 *  week — and the four metric rows, steps, heart rate, sleep and water, each already in the
 *  backend's own plain words. */
export const healthOverview = (token: string, profileId: string, language: string) =>
  api<HealthOverviewOut>(`/profiles/${profileId}/health/overview`, { token, query: { language } });

/** Common foods, for their labels — a tap instead of typing, and how his own words are shown
 *  back to him when a catalogue id is all a meal carries. No token: it holds no key context. */
export const foodCatalog = (language: string) => api<FoodCatalogItemOut[]>("/food-catalog", { query: { language } });

/** What he has logged to eat, oldest first — narrowed to `[since, until)` for the Health tab's
 *  day. "No breakfast" is an entry (`status: "skipped"`), not a missing one. */
export const food = (token: string, profileId: string, language: string, since?: string, until?: string) =>
  api<FoodEntryOut[]>(`/profiles/${profileId}/food`, { token, query: { language, since, until } });

/** Log one number for steps, heart rate, sleep or water — or, for steps and water, log it as
 *  skipped. Home's "Things to do" writes here, through his own explicit Save (E14, the confirm
 *  flow every reading takes: nothing is sent while he is still typing). */
export const metricLog = (token: string, profileId: string, kind: MetricKind, body: MetricLogIn) =>
  api<MetricEntryOut>(`/profiles/${profileId}/metrics/${kind}`, { method: "POST", token, body });

/** Log one meal — a catalogue id, his own words, or both — or that he did not have it. */
export const foodAdd = (token: string, profileId: string, body: FoodLogIn, language: string) =>
  api<FoodEntryOut>(`/profiles/${profileId}/food`, { method: "POST", token, body, query: { language } });

/** A word on the feeling strip (E17), as the phone held it while offline. */
export const feeling = (token: string, profileId: string, word: string, language: string) =>
  api<unknown>(`/profiles/${profileId}/feelings`, { method: "POST", token, body: { word, language } });

/** The emergency card, rendered now from State, in his language (E13-01). */
export const emergencyCard = (token: string, profileId: string, language: string) =>
  api<EmergencyCardOut>(`/profiles/${profileId}/emergency-card`, { token, query: { language } });

/** His whole insurance ledger (T2): every claim ever filed, with the year's totals, in his
 *  language and his region's currency. Money's one door: a caregiver or a viewer without it
 *  is refused (`OutOfScope`, 403). */
export const insuranceLedger = (token: string, profileId: string, language: string) =>
  api<LedgerOut>(`/profiles/${profileId}/insurance/ledger`, { token, query: { language } });

/** The proud number, counted by the backend from the DOSE_TAKEN events in one audited read. */
export const proud = (token: string, profileId: string) =>
  api<ProudOut>(`/profiles/${profileId}/proud`, { token });

/** His policies (E13-03): every one on the profile, newest of each lineage — under
 *  `Scope.MONEY`, the door already reserved for his insurance letters. */
export const policies = (token: string, profileId: string) =>
  api<PolicyOut[]>(`/profiles/${profileId}/insurance/policies`, { token });

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

/** The same question, streamed (docs/design-direction.md "Conversation, waiting and
 *  thinking"): `onStep` for each real part of his record read as it happens, `onDelta` (when
 *  given) for each chunk of the agent asker's own answer text as it is sent — the rule-based
 *  asker never calls it, its answer arriving whole — resolving with the finished answer, the
 *  same `AnswerOut` `ask` returns, so a caller can treat the two the same once the promise
 *  settles. A refusal (`OutOfScope`, a malformed question) throws `Refused`, exactly as `ask`
 *  throws it. */
export function askStream(
  token: string,
  profileId: string,
  question: string,
  mode: AskMode,
  language: string,
  onStep: (key: string, label: string, name: string) => void,
  onDelta?: (text: string) => void,
): Promise<AnswerOut> {
  return new Promise((resolve, reject) => {
    let settled = false;
    apiStream(`/profiles/${profileId}/ask/stream`, { method: "POST", token, body: { question, mode, language } }, (event) => {
      const streamed = event as unknown as AskStreamEvent;
      if (streamed.type === "step") onStep(streamed.key, streamed.label, streamed.name);
      else if (streamed.type === "answer_delta") onDelta?.(streamed.text);
      else if (streamed.type === "answer") {
        settled = true;
        resolve(streamed.answer);
      }
      // A "refusal" event is thrown by `apiStream` itself before it ever reaches `onEvent`.
    })
      .then(() => {
        if (!settled) reject(new Error("the stream ended with no answer"));
      })
      .catch(reject);
  });
}

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

const uploads = (profileId: string, appointmentId: string) => `/profiles/${profileId}/appointments/${appointmentId}/recording/uploads`;

/** A visit's recording sent in chunks as it is made (#129): opened as the microphone opens. */
export const openUpload = (token: string, profileId: string, appointmentId: string, contentType: string, startedAt: string) =>
  api<UploadOut>(uploads(profileId, appointmentId), { method: "POST", token, body: { content_type: contentType, started_at: startedAt } });

/** How far it has come: where to start again after a dropped connection. */
export const uploadStatus = (token: string, profileId: string, appointmentId: string, uploadId: string) =>
  api<UploadOut>(`${uploads(profileId, appointmentId)}/${uploadId}`, { token });

/** One chunk: the recorder's bytes, from where the server got to. */
export const uploadChunk = (token: string, profileId: string, appointmentId: string, uploadId: string, position: number, bytes: Blob) =>
  apiBytes<UploadOut>(`${uploads(profileId, appointmentId)}/${uploadId}/chunks/${position}`, bytes, "application/octet-stream", { method: "PUT", token });

/** The doctor said yes: the recording may be kept, on Stop. */
export const doctorSaidYes = (token: string, profileId: string, appointmentId: string, uploadId: string) =>
  api<UploadOut>(`${uploads(profileId, appointmentId)}/${uploadId}/yes`, { method: "POST", token });

/** Stop: the chunks put together on the server, heard, and read into the post-visit card. */
export const finishUpload = (token: string, profileId: string, appointmentId: string, uploadId: string, durationS: number) =>
  api<ConsultOut>(`${uploads(profileId, appointmentId)}/${uploadId}/finish`, {
    method: "POST",
    token,
    slow: true,
    query: { duration_s: durationS.toFixed(1) },
  });

/** The doctor said no, or the page was left before he answered: every chunk already sent is
 *  thrown away. Goes even as the page goes. */
export const discardUpload = (token: string, profileId: string, appointmentId: string, uploadId: string, because: "no" | "left" | "whole") =>
  sendAndForget(`${uploads(profileId, appointmentId)}/${uploadId}`, { method: "DELETE", token, query: { because } });

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

// --- W5: the Record ------------------------------------------------------------------------

/** The spine's three anchors and one page of visits and illnesses, newest first (E03-01). */
export const timeline = (token: string, profileId: string, language: string, cursor?: string, limit = 10) =>
  api<TimelineOut>(`/profiles/${profileId}/timeline`, { token, query: { language, cursor, limit: String(limit) } });

/** One illness, what is filed with it, and the visits during it (E03-02). */
export const episode = (token: string, profileId: string, episodeId: string) =>
  api<EpisodeViewOut>(`/profiles/${profileId}/episodes/${episodeId}`, { token });

/** The yes to putting this paper with this illness (subject `attach`). */
export const mintAttach = (token: string, profileId: string, artifactId: string, episodeId: string) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "attach", artifact_id: artifactId, episode_id: episodeId },
  });

export const attachToEpisode = (token: string, profileId: string, episodeId: string, artifactId: string, confirmationId: string) =>
  api<unknown>(`/profiles/${profileId}/episodes/${episodeId}/attach`, {
    method: "POST",
    token,
    body: { artifact_id: artifactId, confirmation_id: confirmationId },
  });

/** The doctors and clinics, with how many visits and the last and the next (E03-03). */
export const providers = (token: string, profileId: string) =>
  api<ProviderSummaryOut[]>(`/profiles/${profileId}/providers`, { token });

export const provider = (token: string, profileId: string, providerId: string) =>
  api<ProviderHistoryOut>(`/profiles/${profileId}/providers/${providerId}`, { token });

/** The chief's one line about a place. A line naming a medicine is `NoteNamesHealth`. */
export const noteOnProvider = (token: string, profileId: string, providerId: string, text: string) =>
  api<PlaceNoteOut>(`/profiles/${profileId}/providers/${providerId}/notes`, { method: "POST", token, body: { text } });

/** What changed since this reader last looked; reading it is looking (E03-04) — unless
 *  `peek`, for a tile that draws itself every time (Home) rather than a screen she came to
 *  read this on: the same words, marking no look and leaving no entry on his trail (#207). */
export const changes = (token: string, profileId: string, language: string, peek?: boolean) =>
  api<ChangesOut>(`/profiles/${profileId}/changes`, { token, query: { language, peek: peek ? "true" : undefined } });

/** One analyte's results against his ranges, the direction in words, the boundary last (E09-01). */
export const trend = (token: string, profileId: string, analyte: string, language: string) =>
  api<TrendOut>(`/profiles/${profileId}/trends/${analyte}`, { token, query: { language } });

/** The day: his lines (`patient`) or her table (`caregiver`) (E10-01). */
export const routine = (token: string, profileId: string, persona: "patient" | "caregiver", language: string) =>
  api<RoutineOut>(`/profiles/${profileId}/routine`, { token, query: { persona, language } });

/** The yes to setting exactly this day (subject `routine`). */
export const mintRoutine = (token: string, profileId: string, day: RoutineDayIn) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, { method: "POST", token, body: { subject: "routine", ...day } });

export const setRoutine = (token: string, profileId: string, day: RoutineDayIn, confirmationId: string, persona: "patient" | "caregiver", language: string) =>
  api<RoutineOut>(`/profiles/${profileId}/routine`, {
    method: "PUT",
    token,
    query: { persona, language },
    body: { ...day, confirmation_id: confirmationId },
  });

/** The story of one medicine, in his language (E04-06). */
export const story = (token: string, profileId: string, lineId: string, language: string) =>
  api<StoryOut>(`/profiles/${profileId}/medicines/${lineId}/story`, { token, query: { language } });

/** One part of the story as a voice note (E04-06): the audio, or `Refused("NotFound", 404)`
 *  when the backend has none for this part — then the phone says the words itself. */
export const storyVoice = (token: string, profileId: string, lineId: string, part: string, language: string) =>
  apiBlob(`/profiles/${profileId}/medicines/${lineId}/story/voice`, { token, query: { part, language } });

/** What this label would do to the list, screened before anything is saved (E04-03),
 *  including a supplement or a TCM remedy — screened the same way a prescription medicine
 *  is. In `language`, or the profile's own. */
export const medicineDraft = (token: string, profileId: string, label: LabelIn, sourceArtifactId: string, language?: string) =>
  api<MedicineDraftOut>(`/profiles/${profileId}/medicines/draft`, { method: "POST", token, query: { language }, body: { label, source_artifact_id: sourceArtifactId } });

export const mintMedicine = (token: string, profileId: string, label: LabelIn, sourceArtifactId: string) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "medicine", label, source_artifact_id: sourceArtifactId },
  });

export const addMedicine = (token: string, profileId: string, label: LabelIn, sourceArtifactId: string, confirmationId: string) =>
  api<ReconciledOut>(`/profiles/${profileId}/medicines`, {
    method: "POST",
    token,
    body: { label, source_artifact_id: sourceArtifactId, confirmation_id: confirmationId },
  });

/** The reorder card's "Ask the family to order." (E04-05), step one: who would be asked, for
 *  which medicine, in his words. Nothing is written. */
export const orderPreview = (token: string, profileId: string, lineId: string, language: string) =>
  api<OrderPreviewOut>(`/profiles/${profileId}/medicines/${lineId}/ask-to-order/preview`, { method: "POST", token, query: { language } });

/** His yes to exactly the person the preview named, for this line (subject `order`). */
export const mintOrder = (token: string, profileId: string, lineId: string, personId: string) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "order", line_id: lineId, person_id: personId },
  });

/** The ask, spending his yes: a task on the family's list, or the one already there today. */
export const askToOrder = (token: string, profileId: string, lineId: string, confirmationId: string, language: string) =>
  api<AskedOut>(`/profiles/${profileId}/medicines/${lineId}/ask-to-order`, {
    method: "POST",
    token,
    query: { language },
    body: { confirmation_id: confirmationId },
  });

/** The yes to adding exactly this many found at home (subject `count_correction`), resting on
 *  the photo of the box or the label when there is one — a high-risk medicine needs it. */
export const mintMore = (token: string, profileId: string, lineId: string, quantity: number, artifactId: string | null = null) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "count_correction", line_id: lineId, quantity, artifact_id: artifactId },
  });

export const addMore = (token: string, profileId: string, lineId: string, quantity: number, confirmationId: string, language: string, artifactId: string | null = null) =>
  api<MoreOut>(`/profiles/${profileId}/medicines/${lineId}/more`, {
    method: "POST",
    token,
    query: { language },
    body: { quantity, confirmation_id: confirmationId, artifact_id: artifactId },
  });

/** The review cards, newest first; `open` for the ones still waiting for a yes (E02-04). */
export const reviewCards = (token: string, profileId: string, openOnly: boolean) =>
  api<ReviewCardOut[]>(`/profiles/${profileId}/review-cards`, { token, query: { open: openOnly ? "true" : undefined } });

/** A photo of a machine's screen, read into a review card with no typing (E02-08). */
export const addScreenPhoto = (token: string, profileId: string, data: string, content_type: string, captured_at: string) =>
  api<ReviewCardOut>(`/profiles/${profileId}/readings/photo`, { method: "POST", token, body: { data, content_type, captured_at } });

// --- W7: the patient's day (E05-01, E05-02, E05-05, E13-02, E14-01, E17, E11-07) ------------

/** The pre-visit brief (E05-01): purpose, what changed, the questions, what to bring. */
export const brief = (token: string, profileId: string, appointmentId: string) =>
  api<BriefOut>(`/profiles/${profileId}/appointments/${appointmentId}/brief`, { token });

/** The questions for a visit, each with its source, and his one card (E05-02). */
export const visitQuestions = (token: string, profileId: string, appointmentId: string) =>
  api<VisitQuestionsOut>(`/profiles/${profileId}/appointments/${appointmentId}/questions`, { token });

/** His yes to one change to the questions: the words as typed, or the one to take off. */
export const mintQuestionYes = (token: string, profileId: string, appointmentId: string, change: QuestionChange) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "question", appointment_id: appointmentId, ...change },
  });

/** Spend that yes on exactly that change. */
export const changeQuestion = (token: string, profileId: string, appointmentId: string, change: QuestionChange, confirmation_id: string) =>
  api<VisitQuestionOut>(`/profiles/${profileId}/appointments/${appointmentId}/questions`, {
    method: "POST",
    token,
    body: { ...change, confirmation_id },
  });

/** The post-visit cards for a visit (E05-05), each with its items. */
export const summaries = (token: string, profileId: string, appointmentId: string) =>
  api<VisitSummaryOut[]>(`/profiles/${profileId}/appointments/${appointmentId}/summaries`, { token });

/** His yes to the whole card as shown: every item, kept or left out. */
export const mintSummaryYes = (token: string, profileId: string, summaryId: string, decisions: ItemDecision[]) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "visit_summary", summary_id: summaryId, decisions },
  });

/** Spend it: memos, the planned follow-up, facts citing the transcript, a flag for a change. */
export const confirmSummary = (
  token: string,
  profileId: string,
  appointmentId: string,
  summaryId: string,
  decisions: ItemDecision[],
  confirmation_id: string,
) =>
  api<SummaryConfirmedOut>(`/profiles/${profileId}/appointments/${appointmentId}/summary/${summaryId}/confirm`, {
    method: "POST",
    token,
    body: { decisions, confirmation_id },
  });

/** The memo card: what the doctor said, one line each, ending on the boundary. */
export const memoCard = (token: string, profileId: string) => api<MemoCardOut>(`/profiles/${profileId}/memos`, { token });

/** The not-feeling-well button (E13-02): his words or his voice in, the card out. Urgent: it
 *  goes ahead of every read still waiting. */
export const notFeelingWell = (token: string, profileId: string, said: Said, language: string) =>
  api<WhatToDoOut>(`/profiles/${profileId}/not-feeling-well`, { method: "POST", token, body: { ...said, language }, urgent: true });

/** The two cards the phone keeps for when it cannot reach Nura (W7). */
export const offlineCards = (token: string, profileId: string, language: string) =>
  api<OfflineCardsOut>(`/profiles/${profileId}/not-feeling-well/offline`, { token, query: { language } });

/** A symptom in his words, by voice or typed: how much and since when are read from them. */
export const logSymptom = (token: string, profileId: string, said: Said, language: string) =>
  api<SymptomLoggedOut>(`/profiles/${profileId}/symptoms`, { method: "POST", token, body: { ...said, language }, urgent: true });

/** The last seven days of symptoms, in plain words with the day's name. */
export const symptomLog = (token: string, profileId: string, language: string) =>
  api<SymptomLogOut>(`/profiles/${profileId}/symptoms`, { token, query: { language } });

/** The feeling cloud now (E17-01): whether it shows, the question, the words. */
export const feelingCloud = (token: string, profileId: string, language: string) =>
  api<CloudOut>(`/profiles/${profileId}/feelings/cloud`, { token, query: { language } });

/** A tap on one word. Urgent: a red word is flagged before anything else is read. */
export const tapFeeling = (token: string, profileId: string, word: string, language: string) =>
  api<FeelingOut>(`/profiles/${profileId}/feelings`, { method: "POST", token, body: { word, language }, urgent: true });

/** His one answer to the one question. Urgent: a yes can make the word red. */
export const answerFeeling = (token: string, profileId: string, tapId: string, answer: string, language: string) =>
  api<AnsweredOut>(`/profiles/${profileId}/feelings/${tapId}/answer`, { method: "POST", token, body: { answer, language }, urgent: true });

/** The day's plan of nudges (E17-03, E11-07): what goes, with its why. */
export const nudgePlan = (token: string, profileId: string) => api<NudgePlanOut>(`/profiles/${profileId}/nudges/plan`, { token });

/** Write the planned nudge down and give it to delivery: the planner's own write. */
export const handOverNudge = (token: string, profileId: string) =>
  api<HandedOverOut>(`/profiles/${profileId}/nudges/plan`, { method: "POST", token });

/** The nudges handed over today, with what this person did with each. */
export const dayNudges = (token: string, profileId: string) => api<DayNudgesOut>(`/profiles/${profileId}/nudges`, { token });

/** What he did with a nudge: accepted or dismissed ("Not today"). */
export const answerNudge = (token: string, profileId: string, nudgeId: string, kind: NudgeAnswer) =>
  api<unknown>(`/profiles/${profileId}/nudges/${nudgeId}/response`, { method: "POST", token, body: { kind } });

/** Today's top three (E11-02): alerts, then reminders, then insights, each with its why. */
export const feedToday = (token: string, profileId: string) => api<FeedPageOut>(`/profiles/${profileId}/feed/today`, { token });

/** The Me page (E17-04): the number that only goes up, in his words. */
export const meSummary = (token: string, profileId: string, language: string) =>
  api<MeSummaryOut>(`/profiles/${profileId}/me-summary`, { token, query: { language } });

/** One card by its id, under the card's own scope: what a push opens (`?open=<id>`, #143). */
export const feedItem = (token: string, profileId: string, itemId: string) =>
  api<FeedItemOut>(`/profiles/${profileId}/feed/${itemId}`, { token });

/** The emergency card as the backend prints it (E00, `GET /profiles/{id}/emergency-card.html`):
 *  one self-contained page, every line the backend's, read with his key and shown as it is. */
export const emergencyCardPage = (token: string, profileId: string, language: string) =>
  apiBlob(`/profiles/${profileId}/emergency-card.html`, { token, query: { language } }).then((page) => page.text());

// --- the feed's richer formats (F1) ---------------------------------------------------------

/** Flush the phone's queue of what he did with his cards (E11-08). */
export const feedEvents = (token: string, profileId: string, events: QueuedEventIn[]) =>
  api<EventsOut>(`/profiles/${profileId}/feed/events`, { token, method: "POST", body: { events } });

/** "Sent to Pa this week": every card made for him since Monday, with its status. */
export const feedWeek = (token: string, profileId: string) => api<SentOut[]>(`/profiles/${profileId}/feed/week`, { token });

/** A clip's still, from Nura's own server (no video platform is asked). */
export const clipPoster = (token: string, profileId: string, itemId: string) =>
  apiBlob(`/profiles/${profileId}/feed/${itemId}/clip/poster`, { token, accept: "image/*" });

/** A clip's captions, WebVTT, in the card's language. */
export const clipCaptions = async (token: string, profileId: string, itemId: string): Promise<string> =>
  (await apiBlob(`/profiles/${profileId}/feed/${itemId}/clip/captions`, { token, accept: "text/vtt" })).text();

/** A clip's excerpt, only where the licence let Nura keep one; a 404 refusal otherwise. */
export const clipVideo = (token: string, profileId: string, itemId: string) =>
  apiBlob(`/profiles/${profileId}/feed/${itemId}/clip/video`, { token, accept: "video/*" });

/** "Watching for Pa": every search the engine runs for him, in the reader's words. */
export const searchJobs = (token: string, profileId: string, language: string) =>
  api<SearchJobOut[]>(`/profiles/${profileId}/search-jobs`, { token, query: { language } });

/** Add a watch: the kind and what for. How often is the kind's own. */
export const addSearchJob = (token: string, profileId: string, kind: JobKind, terms: string[]) =>
  api<SearchJobOut>(`/profiles/${profileId}/search-jobs`, { token, method: "POST", body: { kind, terms } });

/** Pause a watch, or resume it. */
export const pauseSearchJob = (token: string, profileId: string, jobId: string, enabled: boolean, language: string) =>
  api<SearchJobOut>(`/profiles/${profileId}/search-jobs/${jobId}`, { token, method: "PATCH", body: { enabled }, query: { language } });

/** His area and the towns it may be (owner, chief). */
export const area = (token: string, profileId: string) => api<AreaOut>(`/profiles/${profileId}/area`, { token });

/** The owner's own yes to setting his area to exactly this value, or to clearing it (#184):
 *  minted for the area shown, spent by setArea. The steward's pre-claim write takes none. */
export const mintAreaConfirmation = (token: string, profileId: string, value: string | null) =>
  api<ConfirmationOut>(`/profiles/${profileId}/confirmations`, {
    method: "POST",
    token,
    body: { subject: "area", area: value },
  });

/** Set his area on his yes, or clear it (null). Once the graph is his, `confirmationId` must
 *  be minted for exactly this value (`mintAreaConfirmation`); the steward's pre-claim write
 *  takes none. */
export const setArea = (token: string, profileId: string, value: string | null, confirmationId?: string) =>
  api<AreaOut>(`/profiles/${profileId}/area`, {
    token,
    method: "PUT",
    body: { area: value, confirmation_id: confirmationId ?? null },
  });

/** "What Nura uses" (RE-05): every family, on or off, and whether this key may set one. */
export const signals = (token: string, profileId: string) =>
  api<SignalsOut>(`/profiles/${profileId}/signals`, { token });

/** Switch one family on or off: his own key, or his chief's. */
export const setSignal = (token: string, profileId: string, family: SignalFamily, on: boolean) =>
  api<SignalsOut>(`/profiles/${profileId}/signals/${family}`, { token, method: "PUT", body: { on } });

/** The ask bar's Web, Videos and Providers filters. Records is `ask`. His words go in the
 *  body, never in the URL, where a log or the browser's history would keep them. */
export const find = (token: string, profileId: string, q: string, where: FindWhere, language: string) =>
  api<FindOut>(`/profiles/${profileId}/find`, { token, method: "POST", body: { q, where, language } });

/** The web and video filters, streamed (docs/design-direction.md): one real step while the
 *  allowlisted search runs, then the results `find` returns. Providers is a directory lookup
 *  with nothing to stream — callers keep using `find` for it. */
export function findStream(
  token: string,
  profileId: string,
  q: string,
  where: "web" | "videos",
  language: string,
  onStep: (key: string, label: string) => void,
): Promise<FindOut> {
  return new Promise((resolve, reject) => {
    let settled = false;
    apiStream(`/profiles/${profileId}/find/stream`, { token, method: "POST", body: { q, where, language } }, (event) => {
      const streamed = event as unknown as FindStreamEvent;
      if (streamed.type === "step") onStep(streamed.key, streamed.label);
      else if (streamed.type === "results") {
        settled = true;
        resolve({ where, results: streamed.results });
      }
    })
      .then(() => {
        if (!settled) reject(new Error("the stream ended with no results"));
      })
      .catch(reject);
  });
}
