import type { ProfileOut } from "../api/types";
import { kvDel, kvGet, kvKeys, kvSet } from "../store/kv";
import type { TodayModel } from "../today/model";

/** The last Today page per profile, kept on the phone so the app opens on it with no
 *  network and no spinner — bound to the key it was read with and good for today only.
 *
 *  An entry names the key (or "owner") and the scope set that read it; a different key or a
 *  narrower scope set finds nothing and the old entry is dropped. It expires at the local
 *  midnight after it was fetched: after that it is deleted and the app shows no dose from it. Any refused
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

export function bindingOf(profile: ProfileOut): Binding {
  return {
    keyId: profile.standing === "owner" ? "owner" : (profile.key_id ?? `${profile.standing}:${profile.role ?? ""}`),
    scopes: [...profile.scopes].sort(),
  };
}

export function sameBinding(a: Binding, b: Binding): boolean {
  return a.keyId === b.keyId && a.scopes.length === b.scopes.length && a.scopes.every((s, i) => s === b.scopes[i]);
}

/** The next local midnight after `now`: the latest a cached page may be shown. */
export function localMidnightAfter(now: Date): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 0, 0);
}

export function isFresh(entry: TodayEntry, now: Date): boolean {
  return new Date(entry.expiresAt).getTime() > now.getTime();
}

export async function saveToday(profileId: string, model: TodayModel, binding: Binding, now: Date): Promise<TodayEntry> {
  const entry: TodayEntry = {
    model,
    binding,
    fetchedAt: now.toISOString(),
    expiresAt: localMidnightAfter(now).toISOString(),
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
  await kvDel(key(profileId));
}

export async function clearAllProfileData(): Promise<void> {
  for (const each of await kvKeys(PREFIX)) await kvDel(each);
}
