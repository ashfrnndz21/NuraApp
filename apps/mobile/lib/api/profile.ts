import { http } from './httpClient';
import { apiConfig } from './config';
import type { Profile, Scope, Standing } from '../../domain/profile';

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
