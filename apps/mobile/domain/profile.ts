/**
 * Typed models mirrored from the real backend (`backend/app/channels/api/schemas.py`,
 * confirmed against the running dev server's own `/openapi.json`, 23 September 2026).
 * `domain/` is the one place these shapes live — `lib/api` returns them, screens read
 * them, nothing re-declares its own copy.
 */

export type Region = 'SG' | 'MY';

export type Scope =
  | 'medicines'
  | 'visits'
  | 'readings'
  | 'records'
  | 'notes'
  | 'money'
  | 'family'
  | 'emergency'
  | 'ask'
  | 'send'
  | 'profile';

export type Standing = 'owner' | 'holder' | 'steward' | 'claimant' | 'none' | 'system';

export interface Profile {
  profileId: string;
  displayName: string;
  language: string;
  region: Region;
  role: string | null;
  scopes: Scope[];
  standing: Standing;
  keyId: string | null;
}
