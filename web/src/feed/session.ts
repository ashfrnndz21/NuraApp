import * as nura from "../api/nura";
import type { ProfileOut, QueuedEventIn } from "../api/types";
import { loadFeed, saveFeed } from "../offline/feedCache";
import { kvGet, kvSet } from "../store/kv";
import { EventQueue } from "./events";
import { bindingOf, clearProfileData, zoneOf } from "../offline/todayCache";
import { voice } from "../player/voice";
import { Playback } from "./playback";
import { FeedStore } from "./store";

/** The feed for the papers open now: one store and one player, kept while he moves between
 *  the pager and Ask, dropped when the papers, the key or its scope set change, and on
 *  sign-out. */

export interface OpenFeed {
  id: string;
  store: FeedStore;
  playback: Playback;
  /** What he did with his cards, kept until the next connection (E11-08). */
  events: EventQueue;
}

let open: OpenFeed | null = null;

export function feedFor(bearer: string, papers: ProfileOut): OpenFeed {
  const binding = bindingOf(papers);
  const id = `${papers.profile_id}|${binding.keyId}|${binding.scopes.join(",")}`;
  if (open?.id === id) return open;
  open?.playback.stop();
  open?.playback.dispose();
  const profileId = papers.profile_id;
  const zone = zoneOf(papers.region);
  const canEngage = papers.standing === "owner" || papers.scopes.includes("records");
  const queued = `feedEvents.${profileId}`;
  const events = new EventQueue({
    load: async () => (await kvGet<QueuedEventIn[]>(queued)) ?? [],
    save: (list) => kvSet(queued, list),
    send: (list) => nura.feedEvents(bearer, profileId, list),
    now: () => new Date(),
    id: () => crypto.randomUUID(),
  });
  const store = new FeedStore({
    first: () => nura.feedPage(bearer, profileId),
    next: (cursor) => nura.feedPage(bearer, profileId, cursor),
    cached: () => nura.feedCached(bearer, profileId),
    keep: {
      load: () => loadFeed(profileId, binding, new Date()),
      save: (page) => saveFeed(profileId, page, binding, new Date(), zone),
      clear: () => clearProfileData(profileId),
    },
    engage: (itemId, event) => nura.engage(bearer, profileId, itemId, event),
    share: (kind) => nura.shareCard(bearer, profileId, kind),
    canEngage,
    now: () => new Date(),
    queue: (itemId, kind) => void events.add(itemId, kind).then(() => events.flush()),
  });
  const playback = new Playback({
    fetchVoice: (itemId, language) => nura.feedVoice(bearer, profileId, itemId, language),
    player: voice,
    onFailure: (failure) => store.say(failure),
    // How much of the voice played, when it stops or ends: a play the first time, a replay
    // after. Seconds of the voice, never of the screen.
    onPlayed: (itemId, seconds, again) => {
      if (canEngage) void events.add(itemId, again ? "replayed" : "played", seconds).then(() => events.flush());
    },
  });
  open = { id, store, playback, events };
  if (canEngage) void events.flush();
  return open;
}

/** Forget the open feed: its voice stops and nothing of it stays in memory. */
export function forgetFeed(): void {
  open?.playback.stop();
  open?.playback.dispose();
  open = null;
}
