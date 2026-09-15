/** What a push opens (#143). The service worker opens `/app/?open=<id>`; the app reads `open`
 *  once, after sign-in is restored, and takes it out of the address so a reload does not open it
 *  again. The id is a card on his feed, or the day's nudge (a push carries no words, so the app
 *  reads them from its region, through the same scoped routes as anything else). A card the key
 *  may not see, or that is not there, and anything else: Today. */

import type { DayNudgesOut, FeedItemOut } from "../api/types";

const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export type Opened = { kind: "card"; item: FeedItemOut } | { kind: "today" };

export interface OpenDeps {
  feedItem(id: string): Promise<FeedItemOut>;
  dayNudges(): Promise<DayNudgesOut>;
}

/** The id in `?open=`, once: read, then taken out of the address. Null when there is none, or
 *  when it is not an id. */
export function takeOpen(
  place: { search: string; pathname: string; hash: string } = window.location,
  history: Pick<History, "replaceState"> = window.history,
): string | null {
  const params = new URLSearchParams(place.search);
  const asked = params.get("open");
  if (asked === null) return null;
  params.delete("open");
  const rest = params.toString();
  history.replaceState(null, "", `${place.pathname}${rest ? `?${rest}` : ""}${place.hash}`);
  return ID.test(asked) ? asked : null;
}

/** Where the id leads: the card by its id, else the day's nudge (which Today shows), else Today. */
export async function resolveOpen(id: string, deps: OpenDeps): Promise<Opened> {
  try {
    return { kind: "card", item: await deps.feedItem(id) };
  } catch {
    // Not a card, or not one this key may see: perhaps the day's nudge, which Today shows.
  }
  try {
    await deps.dayNudges();
  } catch {
    // Nothing more to try: Today.
  }
  return { kind: "today" };
}
