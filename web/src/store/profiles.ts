import { signal } from "@preact/signals";
import * as nura from "../api/nura";
import type { ProfileOut } from "../api/types";
import { language } from "../strings";
import { token } from "./session";

/** Every set of papers this person can open: their own, and each one a key of theirs opens
 *  (product-reset.md §6 — one app, one account, a switcher between the profiles a person owns
 *  or holds keys to). The doors answer this; it is kept here so the switcher in the header
 *  opens on what is already known and reads again behind it, which is what lets a key granted
 *  a moment ago show up without a sign-out.
 *
 *  Only what the backend opened. Nothing here decides what a key may see: each profile carries
 *  its own scopes, and every read is the backend's to allow. */
export const known = signal<readonly ProfileOut[] | null>(null);

/** True while the list is being read again, so the sheet can say it is looking. */
export const looking = signal(false);

/** True when the last read did not answer: the sheet says so rather than showing a list that
 *  may no longer be true. */
export const unreached = signal(false);

export async function refreshKnown(): Promise<void> {
  const bearer = token.value;
  if (!bearer) {
    known.value = null;
    return;
  }
  looking.value = true;
  try {
    const doors = await nura.doors(bearer, language.value);
    known.value = [doors.own, ...doors.invited, ...doors.stewarding].filter((each): each is ProfileOut => each !== null);
    unreached.value = false;
  } catch (failure) {
    // What was known may have been closed since. A list that could not be read again is not
    // shown as though it were current: it goes, and the sheet says Nura could not look.
    known.value = null;
    unreached.value = true;
    throw failure;
  } finally {
    looking.value = false;
  }
}

/** Forget whose papers this person could open. Called at sign-out and whenever the token
 *  changes, so the next person on a shared phone never sees the last one's names. */
export function forgetKnown(): void {
  known.value = null;
  unreached.value = false;
}
