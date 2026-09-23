/**
 * A REST route's refusal body is `{"refusal": "<ClassName>", ...}` —
 * never a sentence (`backend/app/channels/api/refusals.py`'s own doc:
 * "the sentence is the app's to write, not this layer's"). This module
 * is that writing: one plain-words {title, why} per refusal this app
 * screen shows today, and an honest, generic fallback for the many
 * refusal classes it does not name yet — never an HTTP code, never the
 * class name itself, on screen (DESIGN_SYSTEM.md §14 / master-spec §29).
 */
import type { ErrorStateProps } from '../../components/states/ErrorState';

export interface ApiRefusal {
  refusal: string;
  scope?: string;
  status: number;
}

export class ApiRefusalError extends Error {
  refusal: string;
  scope?: string;
  status: number;

  constructor(body: ApiRefusal) {
    super(`Nura API refused: ${body.refusal}`);
    this.name = 'ApiRefusalError';
    this.refusal = body.refusal;
    this.scope = body.scope;
    this.status = body.status;
  }
}

const SCOPE_WORD: Record<string, string> = {
  medicines: 'medicines',
  visits: 'visits',
  readings: 'readings',
  records: 'records',
  notes: 'notes',
  money: 'insurance and money',
  family: 'family',
  emergency: 'emergency details',
  ask: 'Ask Nura',
  send: 'sending',
  profile: 'this profile',
};

/** Named refusal → {title, why}. Not exhaustive (refusals.py names ~80 classes) — see module doc. */
const KNOWN: Record<string, (refusal: ApiRefusal) => { title: string; why: string }> = {
  OutOfScope: (r) => ({
    title: "This needs a wider key.",
    why: `The key open right now doesn't cover ${SCOPE_WORD[r.scope ?? ''] ?? 'that part of the record'}.`,
  }),
  NoConsent: () => ({
    title: 'We need your agreement first.',
    why: 'Nothing was changed. Give consent to continue.',
  }),
  NotTheirsToRead: () => ({
    title: "That's not open to this key.",
    why: 'Nothing was changed or shared.',
  }),
  NotTheOwner: () => ({
    title: 'Only the profile owner can do that.',
    why: 'Nothing was changed.',
  }),
  ProfileAlreadyOwned: () => ({
    title: 'You already have a profile with Nura.',
    why: 'Sign in again and we’ll take you straight there.',
  }),
  // A-013: a wrong sign-in code gets its own calm line, not the generic fallback.
  WrongCode: () => ({
    title: 'That code doesn’t match.',
    why: 'Check the code we sent and try again.',
  }),
  ChallengeExpired: () => ({
    title: 'That code has expired.',
    why: 'Codes are only good for a few minutes. Ask for a new one.',
  }),
  ChallengeLocked: () => ({
    title: 'Too many tries.',
    why: 'For your safety, wait a few minutes before trying again.',
  }),
  NoOpenChallenge: () => ({
    title: 'That code has expired.',
    why: 'Ask for a new one and try again.',
  }),
};

/**
 * `title`/`why`/`ctaLabel` for `ErrorState` (never `onPress`, which is
 * the caller's — retry, go back, or open settings depending on screen).
 */
export function errorStateFromRefusal(
  refusal: ApiRefusal,
): Pick<ErrorStateProps, 'title' | 'why' | 'ctaLabel'> {
  const known = KNOWN[refusal.refusal];
  if (known) {
    return { ...known(refusal), ctaLabel: 'Try again' };
  }
  return {
    title: "We couldn't do that right now.",
    why: 'Nothing was lost. Your own information is still here, and you can try again.',
    ctaLabel: 'Try again',
  };
}
