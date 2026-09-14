import type { ProfileOut } from "../api/types";
import { kvDel, kvGet, kvKeys, kvSet } from "../store/kv";
import type { TodayModel } from "../today/model";

/** The last Today page per profile, kept on the phone so the app opens on it with no
 *  network and no spinner — bound to the key it was read with and good for today only.
 *
 *  An entry names the key (or "owner") and the scope set that read it; a different key or a
 *  narrower scope set finds nothing and the old entry is dropped. It expires at the
 *  midnight after it was fetched on the region's wall clock: after that it is deleted and the app shows no dose from it. Any refused
 *  refresh clears it (`clearProfileData`); sign-out clears every profile's. */

export interface Binding {
  keyId: string;
  scopes: string[];
}

export interface TodayEntry {
  model: TodayModel;
  binding: Binding;
  fetchedAt: string;
  expiresAt: string;
}

const PREFIX = "today.";
const key = (profileId: string) => `${PREFIX}${profileId}`;
/** Everything the phone keeps of a profile's papers: Today's page, the feed's first page
 *  (`feedCache.ts`), the taps held while offline (`queue.ts`), the emergency card
 *  (`emergencyCache.ts`) and the not-feeling-well cards for no network (`day/offline.ts`). A
 *  refusal, a switch of profile and sign-out drop them together. */
export const KEPT_PREFIXES = [PREFIX, "feed.", "queue.", "emergency.", "nfw."] as const;

export function bindingOf(profile: ProfileOut): Binding {
  return {
    keyId: profile.standing === "owner" ? "owner" : (profile.key_id ?? `${profile.standing}:${profile.role ?? ""}`),
    scopes: [...profile.scopes].sort(),
  };
}

export function sameBinding(a: Binding, b: Binding): boolean {
  return a.keyId === b.keyId && a.scopes.length === b.scopes.length && a.scopes.every((s, i) => s === b.scopes[i]);
}

/** The wall clock the papers live on: the profile's region decides, never the phone's zone. */
export const REGION_ZONE: Record<string, string> = { SG: "Asia/Singapore", MY: "Asia/Kuala_Lumpur" };

export function zoneOf(region: string | null | undefined): string {
  return REGION_ZONE[region ?? ""] ?? "Asia/Singapore";
}

/** The next midnight after `now` on the wall clock of `zone`: the latest a kept page may be
 *  shown. The same instant whatever zone the phone itself is set to. */
export function midnightAfter(now: Date, zone: string): Date {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    hourCycle: "h23",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    second: "numeric",
  }).formatToParts(now);
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  const wall = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  const offset = wall - Math.floor(now.getTime() / 1000) * 1000;
  return new Date(Date.UTC(get("year"), get("month") - 1, get("day") + 1) - offset);
}

/** Until when a page may be shown: a kept page's expiry, or the midnight after it was read on
 *  the region's clock. Past it, the page is yesterday's and shows no dose. */
export function shownUntil(fetchedAt: string, keptExpiresAt: string | null, zone: string): Date {
  return keptExpiresAt ? new Date(keptExpiresAt) : midnightAfter(new Date(fetchedAt), zone);
}

export function isFresh(entry: TodayEntry, now: Date): boolean {
  return new Date(entry.expiresAt).getTime() > now.getTime();
}

export async function saveToday(
  profileId: string,
  model: TodayModel,
  binding: Binding,
  now: Date,
  zone: string,
): Promise<TodayEntry> {
  const entry: TodayEntry = {
    model,
    binding,
    fetchedAt: now.toISOString(),
    expiresAt: midnightAfter(now, zone).toISOString(),
  };
  await kvSet(key(profileId), entry);
  return entry;
}

/** The kept page for this profile under this binding, or nothing. A page kept under another
 *  key or a narrower scope set, or one past its midnight, is deleted, not returned: the phone
 *  holds no page it may no longer show. */
export async function loadToday(profileId: string, binding: Binding, now: Date): Promise<TodayEntry | null> {
  const entry = await kvGet<TodayEntry>(key(profileId));
  if (!entry) return null;
  if (!entry.binding || !sameBinding(entry.binding, binding) || !isFresh(entry, now)) {
    await kvDel(key(profileId));
    return null;
  }
  return entry;
}

export async function clearProfileData(profileId: string): Promise<void> {
  for (const prefix of KEPT_PREFIXES) await kvDel(`${prefix}${profileId}`);
}

export async function clearAllProfileData(): Promise<void> {
  for (const prefix of KEPT_PREFIXES) for (const each of await kvKeys(prefix)) await kvDel(each);
}
