import { api } from "./client";
import type {
  AuditOut,
  ClaimableOut,
  ConfirmationOut,
  DoorsOut,
  LineOut,
  MeOut,
  ProfileOut,
  ReadingOut,
  SessionOut,
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

export const medicinesAudit = (token: string, profileId: string) =>
  api<AuditOut[]>(`/profiles/${profileId}/audit`, {
    token,
    query: { scope: "medicines", action: "write", limit: "500" },
  });

export const addReading = (token: string, profileId: string, systolic: number, diastolic: number) =>
  api<ReadingOut>(`/profiles/${profileId}/readings`, {
    method: "POST",
    token,
    body: { systolic, diastolic },
  });
