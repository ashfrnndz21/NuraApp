import type { CallOut, DigestEntryOut } from "../api/familyTypes";
import type { FeedItemOut } from "../api/types";
import { variantOf } from "../feed/model";

/** Connect's own shaping (docs/design/nura-concept-board.html, the Connect screen): kept apart
 *  from `screens/Connect.tsx` so the empty states — no call scheduled, no family yet — and the
 *  picks each section makes are tested without a DOM (`tests/unit/connect.test.ts`), the same
 *  way `today/model.ts` and `family/model.ts` keep their screens' own logic out of the JSX. */

/** The soonest call still ahead, or none: the backend's own order (`upcoming_calls`, soonest
 *  first), read once here so "no call scheduled" is one branch, not a length check scattered
 *  through the screen. */
export function nextCall(calls: readonly CallOut[]): CallOut | null {
  return calls[0] ?? null;
}

/** "Near you": the feed's own local cards (`ChiefPanels.tsx`'s same `local` kind — dengue,
 *  haze, heat, an event near his area), the backend's order, capped so the section stays one
 *  glance. Never a stub: with none today, the section says so instead. */
export function localFeedItems(items: readonly FeedItemOut[], limit = 3): FeedItemOut[] {
  return items.filter((item) => variantOf(item) === "local").slice(0, limit);
}

/** "Messages": the digest's own freshest lines (`family/Thread.tsx`'s same digest) — an entry
 *  with nothing to say (`lines` empty) is not a message, so it is left out before the cap. */
export function freshMessages(entries: readonly DigestEntryOut[], limit = 2): DigestEntryOut[] {
  return entries.filter((entry) => entry.lines.length > 0).slice(0, limit);
}

/** What "Call" dials: the phone's own `tel:` scheme over the number the backend named
 *  (`CallOut.with_person_phone_e164`) — never composed from anything he typed here. */
export function telHref(phone: string): string {
  return `tel:${phone}`;
}
