import { Refused, Unreachable } from "../api/client";
import type { EventsOut, QueuedEventIn } from "../api/types";

/** What he did with his cards, kept on the phone and sent on the next connection (E11-08,
 *  docs/health-feed-spec.md §6 "Analytics"): opened, played (with how many seconds of the
 *  voice note or clip played), replayed, asked more, shared. The backend writes each once by
 *  the id given here, at the moment it happened, and adapts the format of his next cards to
 *  what he opens — never to how long he looked.
 *
 *  **Never time in the feed.** Only a play or a replay carries seconds, and those are the
 *  seconds of the voice or the clip, not of the screen: there is no call here that takes how
 *  long a card was on screen, and nothing is measured while he reads. "Opened" is once per
 *  card, or not at all (`tests/unit/events.test.ts` holds this).
 *
 *  A lost network keeps the queue for next time; a refusal (a key that may not write what he
 *  did) drops it, because a no is not asked again. Nothing here is sent anywhere but Nura's
 *  own server, and the queue is deleted with everything else of these papers. */

export type QueuedKind = "opened" | "played" | "replayed" | "asked_more" | "shared";

const PLAYS: ReadonlySet<QueuedKind> = new Set(["played", "replayed"]);

/** The most events one flush carries: the backend's own limit. */
export const FLUSH_LIMIT = 200;
/** The longest a play can be said to have lasted: a clip or a voice note is under a minute,
 *  and the backend refuses more than ten. */
const LONGEST_PLAY = 600;

export interface EventQueueDeps {
  load(): Promise<QueuedEventIn[]>;
  save(events: QueuedEventIn[]): Promise<void>;
  send(events: QueuedEventIn[]): Promise<EventsOut>;
  now(): Date;
  /** A fresh id for each event, so the same event sent twice is written once. */
  id(): string;
}

export class EventQueue {
  private flushing: Promise<void> | null = null;
  private pending: Promise<void> = Promise.resolve();

  constructor(private readonly deps: EventQueueDeps) {}

  /** Keep one event. `seconds` only on a play or a replay: how much of the voice or clip played. */
  add(itemId: string, event: QueuedKind, seconds: number | null = null): Promise<void> {
    const played = PLAYS.has(event) && seconds !== null && Number.isFinite(seconds) ? Math.min(LONGEST_PLAY, Math.max(0, Math.round(seconds * 10) / 10)) : null;
    const one: QueuedEventIn = { client_id: this.deps.id(), item_id: itemId, event, at: this.deps.now().toISOString(), channel: "app", seconds: played };
    // One write at a time, in the order the events happened.
    this.pending = this.pending.then(async () => {
      const kept = await this.deps.load();
      await this.deps.save([...kept, one]);
    });
    return this.pending;
  }

  /** Send what is kept, a batch at a time. Written and skipped are both forgotten; a lost
   *  network keeps them; a refusal forgets them. One flush at a time. */
  flush(): Promise<void> {
    this.flushing ??= this.send().finally(() => (this.flushing = null));
    return this.flushing;
  }

  private async send(): Promise<void> {
    await this.pending;
    for (;;) {
      const kept = await this.deps.load();
      if (kept.length === 0) return;
      const batch = kept.slice(0, FLUSH_LIMIT);
      try {
        // The backend answers every event it was sent, written or skipped (already written,
        // too old, a card this key does not cover): either way it is not sent again.
        await this.deps.send(batch);
        await this.forget(batch.map((one) => one.client_id));
      } catch (failure) {
        if (failure instanceof Unreachable) return;
        if (failure instanceof Refused) await this.forget(batch.map((one) => one.client_id));
        return;
      }
    }
  }

  private async forget(ids: string[]): Promise<void> {
    const gone = new Set(ids);
    this.pending = this.pending.then(async () => {
      const kept = await this.deps.load();
      await this.deps.save(kept.filter((one) => !gone.has(one.client_id)));
    });
    await this.pending;
  }
}
