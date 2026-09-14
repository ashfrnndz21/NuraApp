import type { FeedPageOut } from "../api/types";
import { kvDel, kvGet, kvSet } from "../store/kv";
import { midnightAfter, sameBinding, type Binding } from "./todayCache";

/** The feed's first page, kept on the phone so the pager opens on it with no network and no
 *  spinner — under the same rules as the Today page (`todayCache.ts`): bound to the key and
 *  the scope set that read it, and good until the midnight after it was read on the profile's
 *  region clock. A page kept under another binding, or past its midnight, is deleted, not
 *  returned. A refusal, a switch of profile and sign-out delete it with the Today page
 *  (`clearProfileData`, `clearAllProfileData`). */

export interface KeptFeed {
  page: FeedPageOut;
  binding: Binding;
  fetchedAt: string;
  expiresAt: string;
}

export const FEED_PREFIX = "feed.";
const key = (profileId: string) => `${FEED_PREFIX}${profileId}`;

export async function saveFeed(
  profileId: string,
  page: FeedPageOut,
  binding: Binding,
  now: Date,
  zone: string,
): Promise<KeptFeed> {
  const entry: KeptFeed = {
    page,
    binding,
    fetchedAt: now.toISOString(),
    expiresAt: midnightAfter(now, zone).toISOString(),
  };
  await kvSet(key(profileId), entry);
  return entry;
}

export function feedIsFresh(entry: Pick<KeptFeed, "expiresAt">, now: Date): boolean {
  return new Date(entry.expiresAt).getTime() > now.getTime();
}

/** Delete the kept feed page if it may no longer be shown — past its midnight, or read under
 *  another binding — without opening the pager. Today calls it on every launch, so an old
 *  page never outlives its midnight on the phone just because the pager was not opened. */
export async function dropStaleFeed(profileId: string, binding: Binding, now: Date): Promise<void> {
  await loadFeed(profileId, binding, now);
}

export async function loadFeed(profileId: string, binding: Binding, now: Date): Promise<KeptFeed | null> {
  const entry = await kvGet<KeptFeed>(key(profileId));
  if (!entry) return null;
  if (!entry.binding || !sameBinding(entry.binding, binding) || !feedIsFresh(entry, now)) {
    await kvDel(key(profileId));
    return null;
  }
  return entry;
}
