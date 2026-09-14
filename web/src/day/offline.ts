import type { OfflineCardsOut } from "../api/types";
import { sameBinding, type Binding } from "../offline/todayCache";
import { kvDel, kvGet, kvSet } from "../store/kv";

/** The two not-feeling-well cards for no network (W7), kept on the phone so that a red word or
 *  the button with no network never shows nothing. Bound, like every page the phone keeps, to
 *  the key and the parts that read it (`todayCache.KEPT_PREFIXES` names this prefix, so a
 *  refusal, a switch of profile and sign-out delete it with the rest). Read again once a day,
 *  and in a new language. */

export const OFFLINE_PREFIX = "nfw.";
const key = (profileId: string) => `${OFFLINE_PREFIX}${profileId}`;
const A_DAY_MS = 24 * 60 * 60 * 1000;

export interface KeptCards {
  cards: OfflineCardsOut;
  binding: Binding;
  fetchedAt: string;
}

export async function keepCards(profileId: string, cards: OfflineCardsOut, binding: Binding, now: Date): Promise<void> {
  const entry: KeptCards = { cards, binding, fetchedAt: now.toISOString() };
  await kvSet(key(profileId), entry);
}

/** The kept cards for these papers under this binding; kept under another key, deleted. */
export async function keptCards(profileId: string, binding: Binding): Promise<KeptCards | null> {
  const entry = await kvGet<KeptCards>(key(profileId));
  if (!entry) return null;
  if (!entry.binding || !sameBinding(entry.binding, binding)) {
    await kvDel(key(profileId));
    return null;
  }
  return entry;
}

/** Whether to read them again: none kept, another language, or kept a day ago. */
export function wantsCards(entry: KeptCards | null, language: string, now: Date): boolean {
  if (!entry) return true;
  if (entry.cards.language !== language) return true;
  return now.getTime() - Date.parse(entry.fetchedAt) >= A_DAY_MS;
}
