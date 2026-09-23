import { http } from './httpClient';
import { apiConfig } from './config';
import type { Profile, Region, Scope, Standing } from '../../domain/profile';

interface ProfileWire {
  profile_id: string;
  display_name: string;
  language: string;
  region: 'SG' | 'MY';
  role: string | null;
  scopes: Scope[];
  standing: Standing;
  key_id: string | null;
}

function fromWire(w: ProfileWire): Profile {
  return {
    profileId: w.profile_id,
    displayName: w.display_name,
    language: w.language,
    region: w.region,
    role: w.role,
    scopes: w.scopes,
    standing: w.standing,
    keyId: w.key_id,
  };
}

export interface ConsentIn {
  wordingVersion: string;
  language: string;
  capturedVia: 'app' | 'whatsapp' | 'paper' | 'verbal_witnessed';
}

/** `POST /profiles/mine` — "who is this for", the profile-owner path (C1). Consent is mandatory, never optional. */
export async function createOwnProfile(
  consent: ConsentIn,
  opts?: { displayName?: string; language?: string },
): Promise<Profile> {
  if (apiConfig.mode === 'demo') {
    return {
      profileId: 'demo-profile',
      displayName: opts?.displayName ?? 'Pa',
      language: opts?.language ?? 'en',
      region: 'SG',
      role: null,
      scopes: ['ask', 'profile'],
      standing: 'owner',
      keyId: null,
    };
  }
  const res = await http.post<ProfileWire>('/profiles/mine', {
    consent: {
      wording_version: consent.wordingVersion,
      language: consent.language,
      captured_via: consent.capturedVia,
    },
    display_name: opts?.displayName ?? null,
    language: opts?.language ?? null,
  });
  return fromWire(res);
}

export type Relationship =
  | 'daughter'
  | 'son'
  | 'spouse'
  | 'sibling'
  | 'grandchild'
  | 'other_family'
  | 'helper'
  | 'friend'
  | 'neighbour'
  | 'other';

/**
 * `POST /profiles/for-someone` — "who is this for" → "my parent" /
 * "someone else" (C1). `basis: 'patient_asked'` is the one basis this
 * screen can honestly claim on its own (`ConsentBasis`'s own doc: "the
 * patient has a phone and asked... the proof is his claim, still to
 * come") — the other four (LPA, a doctor's letter, a witnessed
 * recording) each need an artefact this screen does not collect, so
 * they are out of scope for the golden path's simple chip conversation.
 */
export async function createProfileForSomeone(
  patientPhoneE164: string,
  displayName: string,
  relationship: Relationship,
  consent: ConsentIn,
  opts?: { language?: string },
): Promise<Profile> {
  if (apiConfig.mode === 'demo') {
    return {
      profileId: 'demo-profile-for-someone',
      displayName,
      language: opts?.language ?? 'en',
      region: 'SG',
      role: null,
      scopes: ['ask', 'profile'],
      standing: 'steward',
      keyId: null,
    };
  }
  const res = await http.post<ProfileWire>('/profiles/for-someone', {
    patient_phone_e164: patientPhoneE164,
    display_name: displayName,
    language: opts?.language ?? 'en',
    consent: {
      wording_version: consent.wordingVersion,
      language: consent.language,
      captured_via: consent.capturedVia,
    },
    basis: 'patient_asked',
    relationship,
  });
  return fromWire(res);
}

export interface Me {
  personId: string;
  displayName: string;
  language: string;
  region: Region;
  phoneE164: string | null;
  email: string | null;
  profileId: string | null;
}

/**
 * `GET /me` — the signed-in person's own record, including `profile_id`
 * when he already owns one. `who.tsx` uses this after a `ProfileAlreadyOwned`
 * refusal (a real, legitimate outcome for a returning demo account, not
 * a failure) to recognise the existing profile instead of showing an error.
 */
export async function getMe(): Promise<Me> {
  const w = await http.get<{
    person_id: string;
    display_name: string;
    language: string;
    region: Region;
    phone_e164: string | null;
    email: string | null;
    profile_id: string | null;
  }>('/me');
  return {
    personId: w.person_id,
    displayName: w.display_name,
    language: w.language,
    region: w.region,
    phoneE164: w.phone_e164,
    email: w.email,
    profileId: w.profile_id,
  };
}

/** `GET /profiles/{id}` — the profile this key opens. */
export async function getProfile(profileId: string): Promise<Profile> {
  if (apiConfig.mode === 'demo') {
    return {
      profileId,
      displayName: 'Pa',
      language: 'en',
      region: 'SG',
      role: null,
      scopes: ['ask', 'profile'],
      standing: 'owner',
      keyId: null,
    };
  }
  return fromWire(await http.get<ProfileWire>(`/profiles/${profileId}`));
}
