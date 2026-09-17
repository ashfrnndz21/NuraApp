import { Refused, Unreachable } from "../api/client";
import * as nura from "../api/nura";
import type { EmergencyCardOut, ProfileOut } from "../api/types";
import { kvDel, kvGet, kvSet } from "../store/kv";
import { midnightAfter, sameBinding, type Binding } from "./todayCache";

/** His emergency card, kept on the phone so it opens with no network (E00-08, E13-01): what a
 *  stranger holding his phone needs — who he is, what he takes, whom to call — as the JSON's
 *  verified lines, and the backend's printable page, so it prints with no network too.
 *
 *  Bound, like every page the phone keeps, to the key and the scope set that read it: another
 *  key, a narrower one, a refusal, a switch of profile and sign-out delete it
 *  (`clearProfileData`, `clearAllProfileData`). Unlike the Today page it is not deleted at
 *  midnight — the card is not today's doses, and a fall at night is when it is needed most
 *  (docs/adr/0010-offline-taps-and-the-emergency-card.md). It is read again once a day, the
 *  first time Today is open with a network after the region's midnight, and every time the
 *  card itself is opened with one; it always says when it was read. */

export interface KeptCard {
  card: EmergencyCardOut;
  /** The backend's printable page for the same card, or null if it could not be read. */
  html: string | null;
  binding: Binding;
  fetchedAt: string;
}

export const EMERGENCY_PREFIX = "emergency.";
const key = (profileId: string) => `${EMERGENCY_PREFIX}${profileId}`;

/** Keep this read as the phone's copy. The card's lines always replace what stood before —
 *  they are what this read is for. The printable page does not: `readCard` already tried it
 *  and a `null` here means that one fetch failed, not that the card has no printable page.
 *  Without `previous` a failed fetch would overwrite a printable page the phone already had
 *  with nothing, and the offline copy — the one thing this cache exists to keep readable and
 *  printable with no network — would lose its Print button to a single bad request. So a
 *  `null` html falls back to `previous`'s, when there is one in his language; a real html
 *  from this read, even empty, always wins.
 *
 *  Gated on language, not just on `previous` existing: the printable page's words are his
 *  language's (E13-01's "two languages on one card"), so a carried-over page from before a
 *  language switch would show the wrong words under a JSON card in the new one, one `fetchedAt`
 *  implying both are equally fresh. A stale-language `previous` is treated the same as none. */
export async function saveCard(
  profileId: string,
  read: { card: EmergencyCardOut; html: string | null },
  binding: Binding,
  now: Date,
  previous?: KeptCard | null,
): Promise<KeptCard> {
  const carryable = previous && previous.card.language === read.card.language;
  const html = read.html ?? (carryable ? previous!.html : null);
  const entry: KeptCard = { card: read.card, html, binding, fetchedAt: now.toISOString() };
  await kvSet(key(profileId), entry);
  return entry;
}

/** The kept card for these papers under this binding, or nothing; a card kept under another
 *  key or a narrower scope set is deleted, not returned. */
export async function loadCard(profileId: string, binding: Binding): Promise<KeptCard | null> {
  const entry = await kvGet<KeptCard>(key(profileId));
  if (!entry) return null;
  if (!entry.binding || !sameBinding(entry.binding, binding)) {
    await kvDel(key(profileId));
    return null;
  }
  return entry;
}

export async function dropCard(profileId: string): Promise<void> {
  await kvDel(key(profileId));
}

/** Whether the kept card should be read again: there is none, it is in another language, or
 *  it was read before the last midnight on the region's clock. */
export function wantsRead(entry: KeptCard | null, language: string, now: Date, zone: string): boolean {
  if (!entry) return true;
  if (entry.card.language !== language) return true;
  return midnightAfter(new Date(entry.fetchedAt), zone).getTime() <= now.getTime();
}

/** Read the card now — its JSON, then its printable page — for keeping. The page's own fetch
 *  is best-effort: if it alone fails, `html` comes back `null` and the card is still kept —
 *  `saveCard` is the one that decides what a `null` here means for the phone's copy. */
export async function readCard(bearer: string, profileId: string, language: string): Promise<{ card: EmergencyCardOut; html: string | null }> {
  const card = await nura.emergencyCard(bearer, profileId, language);
  let html: string | null = null;
  try {
    html = await nura.emergencyCardPage(bearer, profileId, language);
  } catch {
    /* printed from the next read */
  }
  return { card, html };
}

/** Refresh the kept card right away, outside `wantsRead`'s once-a-day gate: called after a
 *  write that changes what the card says, such as a new medicine (#171) — a paramedic reading
 *  the kept copy that same day must not find yesterday's list. Best-effort: the write it
 *  follows already succeeded on its own, so a failure here (no network, a server that could
 *  not answer) never surfaces — the kept card simply stands until the next read earns a
 *  fresher one, exactly as `keepsCard` already decides for every other read. */
export async function refreshCardNow(bearer: string, profileId: string, binding: Binding, language: string, now: Date): Promise<void> {
  try {
    const had = await loadCard(profileId, binding);
    await saveCard(profileId, await readCard(bearer, profileId, language), binding, now, had);
  } catch {
    /* the write stands; the kept card catches up on the next read */
  }
}

/** What a failed read of the card means for the copy the phone has: no network, a server that
 *  could not answer, or a State behind the record keep it; a no to this key deletes it. */
export function keepsCard(failure: unknown): boolean {
  return (
    failure instanceof Unreachable ||
    (failure instanceof Refused && (failure.status >= 500 || failure.refusal === "StaleState" || failure.refusal === "NoState"))
  );
}

/** A key that opens the emergency card and nothing else of the papers (checkpoint 14's
 *  neighbour): its whole app is the card. */
export function emergencyOnly(papers: Pick<ProfileOut, "standing" | "scopes">): boolean {
  if (papers.standing === "owner") return false;
  return papers.scopes.includes("emergency") && papers.scopes.every((scope) => scope === "emergency" || scope === "profile");
}
