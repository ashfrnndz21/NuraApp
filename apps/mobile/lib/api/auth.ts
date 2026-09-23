/**
 * The code sign-in flow — `POST /auth/phone/{start,verify}` — and the
 * dev-only quick sign-in the fixture demo profiles use
 * (`NURA_DEV_CODE_SENDER=1`, never available outside a dev run).
 */
import { http } from './httpClient';
import { apiConfig, setSessionToken } from './config';
import type { Region } from '../../domain/profile';

export interface PhoneStartResult {
  expiresInSeconds: number;
}

export interface SignedIn {
  token: string;
  personId: string;
  region: Region;
}

/** `POST /auth/phone/start` — sends a login code to `phoneE164` (logged to the terminal in dev). */
export async function startPhoneSignIn(
  phoneE164: string,
  opts?: { displayName?: string; language?: 'en' | 'ms' | 'zh' },
): Promise<PhoneStartResult> {
  if (apiConfig.mode === 'demo') return { expiresInSeconds: 300 };
  const res = await http.post<{ expires_in_seconds: number }>('/auth/phone/start', {
    phone_e164: phoneE164,
    display_name: opts?.displayName ?? null,
    language: opts?.language ?? null,
  });
  return { expiresInSeconds: res.expires_in_seconds };
}

/** `POST /auth/phone/verify` — the code from `startPhoneSignIn`. Stores the session token on success. */
export async function verifyPhoneSignIn(phoneE164: string, code: string): Promise<SignedIn> {
  if (apiConfig.mode === 'demo') {
    const signedIn = { token: 'demo-token', personId: 'demo-person', region: 'SG' as Region };
    setSessionToken(signedIn.token);
    return signedIn;
  }
  const res = await http.post<{ token: string; person_id: string; region: Region }>('/auth/phone/verify', {
    phone_e164: phoneE164,
    code,
  });
  setSessionToken(res.token);
  return { token: res.token, personId: res.person_id, region: res.region };
}

/** `POST /dev/quick-signin` — the demo profiles only (Pa/Mei), never available outside a dev run. */
export async function devQuickSignIn(as: 'pa' | 'mei'): Promise<SignedIn> {
  const res = await http.post<{ token: string; person_id: string; region: Region }>('/dev/quick-signin', { as });
  setSessionToken(res.token);
  return { token: res.token, personId: res.person_id, region: res.region };
}
