import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import type { EngagementEvent, FeedPageOut, ThreadCardKind } from "../../src/api/types";
import type { KeptFeed } from "../../src/offline/feedCache";
import { FeedStore, type FeedDeps } from "../../src/feed/store";
import { item, learning, page } from "./feedFixtures";

const NOW = new Date("2026-09-14T02:00:00Z"); // 10:00 in Singapore

/** A backend of pages: the first page, then one page per cursor, the story and learning
 *  cards cycling past the gate the way `rank._endless` does. */
function backend(first: FeedPageOut, more: (n: number) => FeedPageOut = (n) => page(tail(n), `c${n}`, `c${n + 1}`)) {
  const asked: string[] = [];
  return {
    asked,
    first: vi.fn(async () => first),
    next: vi.fn(async (cursor: string) => {
      asked.push(cursor);
      return more(Number(cursor.slice(1)));
    }),
  };
}

const tail = (n: number) => [item("story", "story", { item_id: "story-a", headline: `story ${n}` }), learning({ item_id: "learn-a" }), item("story", "story", { item_id: "story-b" })];

const FIRST = page(
  [item("flag", "flag", { item_id: "flag" }), item("now", "now", { item_id: "now" }), item("reading", "today", { item_id: "reading" }), item("gate", "gate", { item_id: "gate" }), item("story", "story", { item_id: "story-a" })],
  null,
  "c1",
);

function store(overrides: Partial<FeedDeps> = {}, api = backend(FIRST)) {
  const kept: { value: KeptFeed | null } = { value: null };
  const engage = vi.fn(async (_id: string, _event: EngagementEvent) => ({}));
  const share = vi.fn(async (_kind: ThreadCardKind) => ({}));
  const deps: FeedDeps = {
    first: api.first,
    next: api.next,
    cached: vi.fn(async () => {
      throw new Refused("NoCachedPage", 404);
    }),
    keep: {
      load: vi.fn(async () => kept.value),
      save: vi.fn(async (p: FeedPageOut) => (kept.value = { page: p, binding: { keyId: "owner", scopes: [] }, fetchedAt: NOW.toISOString(), expiresAt: "2026-09-14T16:00:00.000Z" })),
      clear: vi.fn(async () => {
        kept.value = null;
      }),
    },
    engage,
    share,
    canEngage: true,
    now: () => NOW,
    ...overrides,
  };
  return { feed: new FeedStore(deps), deps, kept, api, engage, share };
}

const ids = (feed: FeedStore) => feed.entries.value.map((entry) => entry.item.item_id);

describe("opening", () => {
  it("shows the first page in the backend's order, the flag first, never re-ranked", async () => {
    const { feed } = store();
    await feed.open();
    expect(ids(feed).slice(0, 5)).toEqual(["flag", "now", "reading", "gate", "story-a"]);
    expect(feed.origin.value).toBe("live");
  });

  it("keeps the fresh first page on the phone", async () => {
    const { feed, deps } = store();
    await feed.open();
    expect(deps.keep.save).toHaveBeenCalledWith(FIRST);
  });

  it("opens on the kept page at once, then the fresh one", async () => {
    const api = backend(FIRST);
    let release: () => void = () => undefined;
    api.first.mockImplementation(() => new Promise((done) => (release = () => done(FIRST))));
    const { feed, kept } = store({}, api);
    kept.value = { page: page([item("now", "now", { item_id: "old-now" })], null, null), binding: { keyId: "owner", scopes: [] }, fetchedAt: "2026-09-14T01:00:00Z", expiresAt: "2026-09-14T16:00:00Z" };
    const opening = feed.open();
    await vi.waitFor(() => expect(ids(feed)).toEqual(["old-now"]));
    expect(feed.origin.value).toBe("kept");
    release();
    await opening;
    expect(ids(feed)[0]).toBe("flag");
  });

  it("uses the backend's cached page when the phone kept none, leaving out what has expired", async () => {
    const api = backend(FIRST);
    let release: () => void = () => undefined;
    api.first.mockImplementation(() => new Promise((done) => (release = () => done(FIRST))));
    const cached = page([item("now", "now", { item_id: "yesterday", expires_at: "2026-09-13T16:00:00Z" }), item("story", "story", { item_id: "kept-story" })], null, "c1");
    const { feed } = store({ cached: vi.fn(async () => cached) }, api);
    const opening = feed.open();
    await vi.waitFor(() => expect(ids(feed)).toEqual(["kept-story"]));
    expect(feed.origin.value).toBe("cached");
    release();
    await opening;
  });

  it("does not move the list under his finger: a fresh page that lands after he has read on is merged in below the card on screen", async () => {
    const api = backend(FIRST);
    let release: () => void = () => undefined;
    api.first.mockImplementation(() => new Promise((done) => (release = () => done(FIRST))));
    const { feed, kept, deps } = store({}, api);
    kept.value = { page: page([item("now", "now", { item_id: "k1" }), item("story", "story", { item_id: "k2" }), item("story", "story", { item_id: "k3" })], null, null), binding: { keyId: "owner", scopes: [] }, fetchedAt: "2026-09-14T01:00:00Z", expiresAt: "2026-09-14T16:00:00Z" };
    const opening = feed.open();
    await vi.waitFor(() => expect(ids(feed)).toEqual(["k1", "k2", "k3"]));
    const before = feed.entries.value.slice(0, 2).map((entry) => entry.key);
    await feed.visible(1);
    release();
    await opening;
    // What he has passed and the card on screen stay put, keys and all; below them, the fresh
    // page in the backend's order — the flag made since is the very next card, not lost.
    expect(feed.entries.value.slice(0, 2).map((entry) => entry.key)).toEqual(before);
    expect(ids(feed).slice(0, 7)).toEqual(["k1", "k2", "flag", "now", "reading", "gate", "story-a"]);
    expect(feed.origin.value).toBe("live");
    expect(deps.keep.save).toHaveBeenCalledWith(FIRST);
    // The pages go on from the fresh page's cursor.
    await feed.visible(5);
    await vi.waitFor(() => expect(api.next).toHaveBeenCalledWith("c1"));
  });

  it("does not repeat a card he has already passed when the fresh page carries it too", async () => {
    const fresh = page([item("now", "now", { item_id: "k1" }), item("memo", "today", { item_id: "memo" }), item("story", "story", { item_id: "k2" })], null, null);
    const api = backend(fresh);
    let release: () => void = () => undefined;
    api.first.mockImplementation(() => new Promise((done) => (release = () => done(fresh))));
    const { feed, kept } = store({}, api);
    kept.value = { page: page([item("now", "now", { item_id: "k1" }), item("story", "story", { item_id: "k2" })], null, null), binding: { keyId: "owner", scopes: [] }, fetchedAt: "2026-09-14T01:00:00Z", expiresAt: "2026-09-14T16:00:00Z" };
    const opening = feed.open();
    await vi.waitFor(() => expect(ids(feed)).toEqual(["k1", "k2"]));
    await feed.visible(1);
    release();
    await opening;
    expect(ids(feed)).toEqual(["k1", "k2", "memo"]);
    expect(new Set(feed.entries.value.map((entry) => entry.key)).size).toBe(3);
  });

  it("drops a page of the old list that lands after the fresh page was merged in", async () => {
    const api = backend(FIRST, (n) => page([item("story", "story", { item_id: `old-${n}` })], `c${n}`, null));
    let release: () => void = () => undefined;
    api.first.mockImplementation(() => new Promise((done) => (release = () => done(page([item("now", "now", { item_id: "fresh-now" })], null, null)))));
    let answer: () => void = () => undefined;
    api.next.mockImplementation((cursor: string) => new Promise((done) => (answer = () => done(page([item("story", "story", { item_id: `old-${cursor}` })], cursor, null)))));
    const { feed, kept } = store({}, api);
    kept.value = { page: page([item("now", "now", { item_id: "k1" }), item("story", "story", { item_id: "k2" })], null, "k-next"), binding: { keyId: "owner", scopes: [] }, fetchedAt: "2026-09-14T01:00:00Z", expiresAt: "2026-09-14T16:00:00Z" };
    const opening = feed.open();
    await vi.waitFor(() => expect(ids(feed)).toEqual(["k1", "k2"]));
    const reading = feed.visible(1); // within two of the end: the kept page's next is asked for
    await vi.waitFor(() => expect(api.next).toHaveBeenCalledWith("k-next"));
    release();
    await vi.waitFor(() => expect(ids(feed)).toEqual(["k1", "k2", "fresh-now"]));
    answer(); // the kept page's next page lands now, after the merge
    await Promise.all([opening, reading]);
    expect(ids(feed)).toEqual(["k1", "k2", "fresh-now"]);
  });

  it("opens once: back from Ask, what was on screen is still there and nothing is asked again", async () => {
    const { feed, api } = store();
    await feed.open();
    await feed.open();
    expect(api.first).toHaveBeenCalledTimes(1);
  });
});

describe("paging", () => {
  it("asks for the next page only within two cards of the end", async () => {
    const { feed, api } = store();
    await feed.open();
    expect(api.next).not.toHaveBeenCalled();
    await feed.visible(1); // three cards after it
    expect(api.next).not.toHaveBeenCalled();
    await feed.visible(2); // two cards after it: the next page
    expect(api.asked).toEqual(["c1"]);
    expect(ids(feed)).toHaveLength(8);
  });

  it("asks for each cursor once, each the one the page before handed back", async () => {
    const { feed, api } = store();
    await feed.open();
    await Promise.all([feed.visible(3), feed.visible(3), feed.visible(4)]);
    for (let at = 5; at < 20; at++) await feed.visible(at);
    expect(api.asked).toEqual([...new Set(api.asked)]);
    expect(api.asked).toEqual(api.asked.map((_, n) => `c${n + 1}`));
  });

  it("pages endlessly past the gate, keying each card by its place since story and learning come round again", async () => {
    const { feed } = store();
    await feed.open();
    for (let at = 0; at < 40; at++) await feed.visible(at);
    const entries = feed.entries.value;
    expect(entries.length).toBeGreaterThan(40);
    const pastGate = entries.slice(ids(feed).indexOf("gate") + 1).map((entry) => entry.item.supply);
    expect(new Set(pastGate)).toEqual(new Set(["story", "learning"]));
    expect(new Set(entries.map((entry) => entry.key)).size).toBe(entries.length);
    expect(feed.ended.value).toBe(false);
  });

  it("stops asking when the backend hands back no cursor", async () => {
    const { feed, api } = store({}, backend(FIRST, () => page([item("story", "story")], "c1", null)));
    await feed.open();
    await feed.visible(4);
    await feed.visible(5);
    expect(api.asked).toEqual(["c1"]);
    expect(feed.ended.value).toBe(true);
  });

  it("says the quiet hours as the backend does: an empty page, no cursor", async () => {
    const { feed } = store({}, backend(page([], null, null, { quiet: true })));
    await feed.open();
    expect(feed.entries.value).toEqual([]);
    expect(feed.quiet.value).toBe(true);
    expect(feed.ended.value).toBe(true);
  });
});

describe("failures", () => {
  it("offline, keeps the kept page on screen and says so", async () => {
    const { feed, kept, deps } = store({ first: vi.fn(async () => Promise.reject(new Unreachable())) });
    kept.value = { page: FIRST, binding: { keyId: "owner", scopes: [] }, fetchedAt: "2026-09-14T01:00:00Z", expiresAt: "2026-09-14T16:00:00Z" };
    await feed.open();
    expect(feed.offline.value).toBe(true);
    expect(feed.origin.value).toBe("kept");
    expect(ids(feed)[0]).toBe("flag");
    expect(deps.keep.clear).not.toHaveBeenCalled();
  });

  it("offline with nothing kept: nothing on screen, nothing spinning", async () => {
    const { feed } = store({ first: vi.fn(async () => Promise.reject(new Unreachable())), cached: vi.fn(async () => Promise.reject(new Unreachable())) });
    await feed.open();
    expect(feed.entries.value).toEqual([]);
    expect(feed.offline.value).toBe(true);
    expect(feed.busy.value).toBe(false);
  });

  it("a refusal deletes what the phone kept, clears the list and is said — never swallowed", async () => {
    const refusal = new Refused("NoKey", 403);
    const { feed, kept, deps } = store({ first: vi.fn(async () => Promise.reject(refusal)) });
    kept.value = { page: FIRST, binding: { keyId: "owner", scopes: [] }, fetchedAt: "2026-09-14T01:00:00Z", expiresAt: "2026-09-14T16:00:00Z" };
    await feed.open();
    expect(deps.keep.clear).toHaveBeenCalled();
    expect(feed.entries.value).toEqual([]);
    expect(feed.error.value).toBe(refusal);
  });

  it("a refused next page is said the same way", async () => {
    const api = backend(FIRST, () => {
      throw new Refused("OutOfScope", 403, "records");
    });
    const { feed, deps } = store({}, api);
    await feed.open();
    await feed.visible(3);
    expect(feed.error.value).toBeInstanceOf(Refused);
    expect(deps.keep.clear).toHaveBeenCalled();
  });

  it("a next page lost to the network is asked for again when he scrolls on", async () => {
    let fail = true;
    const api = backend(FIRST, (n) => {
      if (fail) throw new Unreachable();
      return page(tail(n), `c${n}`, `c${n + 1}`);
    });
    const { feed } = store({}, api);
    await feed.open();
    await feed.visible(3);
    expect(feed.offline.value).toBe(true);
    fail = false;
    await feed.visible(3);
    expect(ids(feed).length).toBe(8);
    expect(feed.offline.value).toBe(false);
  });
});

describe("side actions", () => {
  it("Not for me posts `dismissed` and the card says so, every copy of it", async () => {
    const { feed, engage } = store();
    await feed.open();
    const card = feed.entries.value[4]!.item;
    await feed.notForMe(card);
    expect(engage).toHaveBeenCalledWith("story-a", "dismissed");
    expect(feed.notes.value.get("story-a")).toBe("declined");
  });

  it("Not for me is sent even by a key that may not write the other events, and a no is said", async () => {
    const refusal = new Refused("OutOfScope", 403, "records");
    const engage = vi.fn(async () => Promise.reject(refusal));
    const { feed } = store({ engage, canEngage: false });
    await feed.open();
    await feed.notForMe(feed.entries.value[2]!.item);
    expect(engage).toHaveBeenCalled();
    expect(feed.said.value).toBe(refusal);
    expect(feed.notes.value.size).toBe(0);
    expect(feed.entries.value).toHaveLength(5); // the list stays
  });

  it("Family sends a reading by reference and says so; a card the thread cannot carry says that", async () => {
    const { feed, share, engage } = store();
    await feed.open();
    await feed.share(feed.entries.value[2]!.item);
    expect(share).toHaveBeenCalledWith("reading");
    expect(feed.notes.value.get("reading")).toBe("shared");
    expect(engage).toHaveBeenCalledWith("reading", "shared");
    await feed.share(feed.entries.value[4]!.item);
    expect(share).toHaveBeenCalledTimes(1);
    expect(feed.notes.value.get("story-a")).toBe("cannotShare");
  });

  it("a refused share is said, never swallowed", async () => {
    const refusal = new Refused("OutOfScope", 403, "family");
    const { feed } = store({ share: vi.fn(async () => Promise.reject(refusal)) });
    await feed.open();
    await feed.share(feed.entries.value[2]!.item);
    expect(feed.said.value).toBe(refusal);
    expect(feed.notes.value.size).toBe(0);
  });

  it("says a card at rest on his screen was opened, once, and only for a key that may", async () => {
    const queue = vi.fn();
    const { feed } = store({ queue });
    await feed.open();
    const first = feed.entries.value[0]!.item;
    feed.seen(first);
    feed.seen(first);
    expect(queue.mock.calls).toEqual([[first.item_id, "opened"]]);
    const narrow = vi.fn();
    const { feed: theirs } = store({ queue: narrow, canEngage: false });
    await theirs.open();
    theirs.seen(theirs.entries.value[0]!.item);
    expect(narrow).not.toHaveBeenCalled();
  });

  it("heard and tapped are written back only by a key that may", async () => {
    const { feed, engage } = store({ canEngage: false });
    await feed.open();
    feed.record(feed.entries.value[1]!.item, "heard");
    expect(engage).not.toHaveBeenCalled();
  });
});
