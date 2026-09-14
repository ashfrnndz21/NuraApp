import { api } from "./client";
import type {
  BiographyIn,
  BiographyOut,
  ClaimableOut,
  ConditionsOut,
  ConfirmationOut,
  ConsentOut,
  DecisionIn,
  DocumentSource,
  DoorsOut,
  KeyOut,
  FeedPageOut,
  LineOut,
  MeOut,
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

/** The keys on the profile with their holders' names: the owner reads whom to call. */
export const keys = (token: string, profileId: string) =>
  api<KeyOut[]>(`/profiles/${profileId}/keys`, { token });

export const addReading = (token: string, profileId: string, systolic: number, diastolic: number) =>
  api<ReadingOut>(`/profiles/${profileId}/readings`, {
    method: "POST",
    token,
    body: { systolic, diastolic },
  });

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

// --- E01: onboarding (mocked by `src/api/mock/` under VITE_API_MOCK=1 until the backend lands) ---

export const conditions = (token: string, language: string) =>
  api<ConditionsOut>("/onboarding/conditions", { token, query: { language } });

export const settings = (token: string, profileId: string) =>
  api<SettingsOut>(`/profiles/${profileId}/settings`, { token });

export const putSettings = (token: string, profileId: string, body: SettingsIn) =>
  api<SettingsOut>(`/profiles/${profileId}/settings`, { method: "PUT", token, body });

export const biography = (token: string, profileId: string, language: string) =>
  api<BiographyOut>(`/profiles/${profileId}/biography`, { token, query: { language } });

/** Open, or update, the biography with the words he tapped; the read-back lines come back. */
export const tellBiography = (token: string, profileId: string, body: BiographyIn) =>
  api<BiographyOut>(`/profiles/${profileId}/biography`, { method: "POST", token, body });

export const answerReadBack = (token: string, profileId: string, line_id: string, answer: "yes" | "no") =>
  api<BiographyOut>(`/profiles/${profileId}/biography/read-back`, { method: "POST", token, body: { line_id, answer } });

/** A paper the person confirmed: the biography takes it in and answers with the next prompt. */
export const addPaper = (token: string, profileId: string, card_id: string, language: string) =>
  api<BiographyOut>(`/profiles/${profileId}/biography/papers`, { method: "POST", token, body: { card_id, language } });

export const answerQuestion = (token: string, profileId: string, question_id: string, keep: boolean) =>
  api<BiographyOut>(`/profiles/${profileId}/biography/questions`, { method: "POST", token, body: { question_id, keep } });

export const closeBiography = (token: string, profileId: string) =>
  api<BiographyOut>(`/profiles/${profileId}/biography/close`, { method: "POST", token });

export const plan = (token: string, profileId: string, language: string) =>
  api<PlanOut>(`/profiles/${profileId}/plan`, { token, query: { language } });

export const laterOnPlan = (token: string, profileId: string, gap_id: string, language: string) =>
  api<PlanOut>(`/profiles/${profileId}/plan/later`, { method: "POST", token, body: { gap_id, language } });

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
