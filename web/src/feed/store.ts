import { signal } from "@preact/signals";
import { Refused, Unreachable } from "../api/client";
import type { EngagementEvent, FeedItemOut, FeedPageOut, ThreadCardKind } from "../api/types";
import type { KeptFeed } from "../offline/feedCache";
import { shareAs } from "./model";

/** The feed as a stream of pages, in the backend's order — flag, now, today, the gate, his
 *  story, learning — never re-ranked here.
 *
 *  It opens on the page the phone kept (key-bound, good until the region's midnight), or else
 *  on the backend's own cached page (`GET …/feed/cached`, the last first page rendered for
 *  him), and then on the fresh first page. It asks for the next page by the cursor the last
 *  one handed back as soon as he is within two cards of the end, and asks for each cursor
 *  once: the same cursor is the same page, so what he has seen never shifts. A fresh first
 *  page that lands after he has read on is merged in below the card on screen — the cards he
 *  has passed and the one he is on stay exactly where they are, and a card made since (a flag,
 *  the post-visit memo) is the next one down, never lost. Past the gate
 *  the backend cycles his story and learning cards, so the list pages on for as long as he
 *  scrolls. A lost network keeps what is on screen; anything else — a refusal first of all —
 *  deletes what the phone kept of these papers and is said, never swallowed.
 *
 *  Nothing here plays audio or moves the screen; it is data only (see `playback.ts`). */

export const PREFETCH_WITHIN = 2;

/** One card at one place in the list. The same item can come back further down — past the
 *  gate the backend cycles the story and learning cards — so a card is keyed by its place
 *  (page and position), never by its id. */
export interface Entry {
  key: string;
  item: FeedItemOut;
}

/** What is on screen came from: nowhere yet; the phone's kept page; the backend's cached
 *  page; the network, fresh. */
export type Origin = "none" | "kept" | "cached" | "live";

/** What a side action left on the card, said under it in the catalogue's words. */
export type Note = "declined" | "shared" | "cannotShare";

export interface FeedDeps {
  first(): Promise<FeedPageOut>;
  next(cursor: string): Promise<FeedPageOut>;
  cached(): Promise<FeedPageOut>;
  keep: {
    load(): Promise<KeptFeed | null>;
    save(page: FeedPageOut): Promise<KeptFeed>;
    /** Delete everything the phone kept of these papers (Today's page too). */
    clear(): Promise<void>;
  };
  engage(itemId: string, event: EngagementEvent): Promise<unknown>;
  share(kind: ThreadCardKind): Promise<unknown>;
  /** Whether this key may write what he did with a card (the owner, or a key with the
   *  records scope, as every event needs). Only for heard, tapped and shared: "Not for me" is
   *  always sent, and a refusal of it is said. */
  canEngage: boolean;
  now(): Date;
}

interface PageMark {
  cursor: string | null;
  next: string | null;
}

export class FeedStore {
  readonly entries = signal<Entry[]>([]);
  readonly origin = signal<Origin>("none");
  /** When the kept page on screen was read, and until when it may be shown. */
  readonly keptAt = signal<string | null>(null);
  readonly keptUntil = signal<string | null>(null);
  readonly offline = signal(false);
  /** A failure reading the feed: the list is gone and this is said instead. */
  readonly error = signal<unknown>(null);
  /** A failure of one action (a share, a "Not for me"): said; the list stays. */
  readonly said = signal<unknown>(null);
  readonly quiet = signal(false);
  readonly ended = signal(false);
  readonly busy = signal(false);
  readonly audience = signal("patient");
  readonly notes = signal<ReadonlyMap<string, Note>>(new Map());
  /** The index of the card on screen. */
  current = 0;

  private pages: PageMark[] = [];
  private asked = new Set<string>();
  /** Every page put on screen gets the next number, never reused: what keys its cards. */
  private serial = 0;
  /** Which list a page answer belongs to: a page asked for before the list was replaced (the
   *  fresh page merged in) is dropped when it lands. */
  private generation = 0;
  private loading: Promise<void> | null = null;
  private opening: Promise<void> | null = null;

  constructor(private readonly deps: FeedDeps) {}

  /** Open once per store: whatever is on screen stays when he goes to Ask and comes back. */
  open(): Promise<void> {
    this.opening ??= this.start();
    return this.opening;
  }

  private async start(): Promise<void> {
    const kept = await this.deps.keep.load();
    if (kept) this.show(kept.page, "kept", kept);
    try {
      if (!kept) {
        const cached = await this.cachedPage();
        if (cached) this.show(cached, "cached");
      }
      const fresh = await this.deps.first();
      this.offline.value = false;
      const saved = await this.deps.keep.save(fresh);
      // The fresh page takes the screen while he is still on the first card; once he is
      // reading on, it is merged in below the card on screen, so nothing moves under his
      // finger and nothing made since is lost.
      if (this.current === 0 || this.entries.value.length === 0) this.show(fresh, "live", saved);
      else this.merge(fresh, saved);
      await this.prefetch();
    } catch (failure) {
      await this.fail(failure);
    }
  }

  /** The backend's cached page, with any card past its own expiry left out. No page yet
   *  (`NoCachedPage`: nothing was ever rendered for this person) is not a "no" — there is
   *  simply nothing to show before the fresh page, which is asked for at once. */
  private async cachedPage(): Promise<FeedPageOut | null> {
    try {
      const page = await this.deps.cached();
      const now = this.deps.now().getTime();
      const items = page.items.filter((item) => new Date(item.expires_at).getTime() > now);
      return items.length > 0 ? { ...page, items } : null;
    } catch (failure) {
      if (failure instanceof Refused && failure.refusal === "NoCachedPage") return null;
      throw failure;
    }
  }

  private show(page: FeedPageOut, origin: Origin, kept?: KeptFeed): void {
    this.generation += 1;
    this.pages = [{ cursor: page.cursor, next: page.next_cursor }];
    this.asked = new Set(page.cursor ? [page.cursor] : []);
    const at = this.serial++;
    this.entries.value = page.items.map((item, index) => ({ key: `${at}:${index}`, item }));
    this.origin.value = origin;
    this.keptAt.value = origin === "kept" && kept ? kept.fetchedAt : null;
    this.keptUntil.value = kept ? kept.expiresAt : null;
    this.quiet.value = page.quiet;
    this.ended.value = page.next_cursor === null;
    this.audience.value = page.audience;
  }

  /** The fresh first page, after he has read on: every card up to and including the one on
   *  screen stays where it is, and below it come the fresh page's cards he has not passed, in
   *  the backend's order — a card made since the kept page is the next one down. The pages
   *  then go on from the fresh page's cursor, so the rest of the list is the live one. */
  private merge(page: FeedPageOut, kept: KeptFeed): void {
    this.generation += 1;
    const shown = this.entries.value;
    const stay = shown.slice(0, Math.min(this.current, shown.length - 1) + 1);
    const passed = new Set(stay.map((entry) => entry.item.item_id));
    const at = this.serial++;
    const below = page.items.filter((item) => !passed.has(item.item_id)).map((item, index) => ({ key: `${at}:${index}`, item }));
    this.pages = [{ cursor: page.cursor, next: page.next_cursor }];
    this.asked = new Set(page.cursor ? [page.cursor] : []);
    this.entries.value = [...stay, ...below];
    this.origin.value = "live";
    this.keptAt.value = null;
    this.keptUntil.value = kept.expiresAt;
    this.quiet.value = page.quiet;
    this.ended.value = page.next_cursor === null;
    this.audience.value = page.audience;
  }

  /** The card at `index` is on screen. Within two of the end, the next page is asked for. */
  visible(index: number): Promise<void> {
    this.current = index;
    return this.prefetch();
  }

  private async prefetch(): Promise<void> {
    if (this.loading) return this.loading;
    const last = this.pages[this.pages.length - 1];
    if (!last?.next || this.asked.has(last.next)) return;
    if (this.entries.value.length - 1 - this.current > PREFETCH_WITHIN) return;
    const cursor = last.next;
    const generation = this.generation;
    this.asked.add(cursor);
    this.busy.value = true;
    let failed = false;
    this.loading = (async () => {
      try {
        const page = await this.deps.next(cursor);
        // The list was replaced while this page was on its way (the fresh page merged in):
        // it belongs to the old list, and the new one asks for its own.
        if (generation !== this.generation) return;
        const at = this.pages.length;
        const serial = this.serial++;
        this.pages.push({ cursor, next: page.next_cursor });
        this.entries.value = [...this.entries.value, ...page.items.map((item, index) => ({ key: `${serial}:${index}`, item }))];
        this.ended.value = page.next_cursor === null || page.items.length === 0;
        if (page.items.length === 0) this.pages[at] = { cursor, next: null };
        this.offline.value = false;
      } catch (failure) {
        failed = true;
        this.asked.delete(cursor); // offline: he may ask again by scrolling once it is back
        await this.fail(failure);
      } finally {
        this.busy.value = false;
        this.loading = null;
      }
    })();
    await this.loading;
    // A short page can leave him within two of the end again.
    if (!failed) await this.prefetch();
  }

  private async fail(failure: unknown): Promise<void> {
    if (failure instanceof Unreachable) {
      this.offline.value = true;
      return;
    }
    // A refusal, or anything that is not a lost network: nothing of these papers stays.
    await this.deps.keep.clear();
    this.pages = [];
    this.asked.clear();
    this.entries.value = [];
    this.origin.value = "none";
    this.keptAt.value = null;
    this.keptUntil.value = null;
    this.error.value = failure;
  }

  private mark(itemId: string, note: Note): void {
    const next = new Map(this.notes.value);
    next.set(itemId, note);
    this.notes.value = next;
  }

  /** A failure of one action, said on the screen; what is shown stays. */
  say(failure: unknown): void {
    if (failure instanceof Unreachable) this.offline.value = true;
    this.said.value = failure;
  }

  /** Heard, tapped, shared: written back when this key may, in the background, and a
   *  refusal of it is said. */
  record(item: FeedItemOut, event: Exclude<EngagementEvent, "dismissed">): void {
    if (!this.deps.canEngage) return;
    this.deps.engage(item.item_id, event).catch((failure: unknown) => this.say(failure));
  }

  /** "Not for me": his word, written back as `dismissed`. The card then says so — every
   *  copy of it further down the list too — and for the owner the backend holds that kind of
   *  card back for the rest of his day. */
  async notForMe(item: FeedItemOut): Promise<void> {
    this.said.value = null;
    try {
      await this.deps.engage(item.item_id, "dismissed");
      this.mark(item.item_id, "declined");
    } catch (failure) {
      this.say(failure);
    }
  }

  /** Family: the card into the family thread, by reference, when the thread can carry its
   *  kind; otherwise the card says it cannot be sent yet. Nothing is sent as words. */
  async share(item: FeedItemOut): Promise<void> {
    this.said.value = null;
    const kind = shareAs(item);
    if (!kind) {
      this.mark(item.item_id, "cannotShare");
      return;
    }
    try {
      await this.deps.share(kind);
      this.mark(item.item_id, "shared");
      this.record(item, "shared");
    } catch (failure) {
      this.say(failure);
    }
  }
}
