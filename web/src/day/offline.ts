import type { OfflineCardsOut } from "../api/types";
import { midnightAfter, sameBinding, type Binding } from "../offline/todayCache";
import { kvDel, kvGet, kvSet } from "../store/kv";

/** The two not-feeling-well cards for no network (W7, ADR 0012), kept on the phone so that a
 *  red word or the button with no network never shows nothing. Bound, like every page the phone
 *  keeps, to the key and the parts that read it (`todayCache.KEPT_PREFIXES` names this prefix,
 *  so a refusal, a switch of profile and sign-out delete it with the rest), and good until the
 *  midnight after it was read on the region's clock, like the Today page (E00-08): past it the
 *  copy is deleted, and with no network the what-to-do screen says the catalogue's copy of the
 *  same card (`day/model.ts` `offlineLines`) — never nothing. Read again once a day, and in a
 *  new language. */

export const OFFLINE_PREFIX = "nfw.";
const key = (profileId: string) => `${OFFLINE_PREFIX}${profileId}`;
const A_DAY_MS = 24 * 60 * 60 * 1000;

export interface KeptCards {
  cards: OfflineCardsOut;
  binding: Binding;
  fetchedAt: string;
  /** The midnight after it was read, on the region's clock: the latest it may be used. */
  expiresAt: string;
}

export async function keepCards(profileId: string, cards: OfflineCardsOut, binding: Binding, now: Date, zone: string): Promise<void> {
  const entry: KeptCards = { cards, binding, fetchedAt: now.toISOString(), expiresAt: midnightAfter(now, zone).toISOString() };
  await kvSet(key(profileId), entry);
}

/** The kept cards for these papers under this binding, before their midnight; kept under another
 *  key, or past their midnight (or kept before they had one), deleted. */
export async function keptCards(profileId: string, binding: Binding, now: Date = new Date()): Promise<KeptCards | null> {
  const entry = await kvGet<KeptCards>(key(profileId));
  if (!entry) return null;
  if (!entry.binding || !sameBinding(entry.binding, binding) || !entry.expiresAt || Date.parse(entry.expiresAt) <= now.getTime()) {
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
