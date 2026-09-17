import { describe, expect, it } from "vitest";
import type { CallOut, DigestEntryOut } from "../../src/api/familyTypes";
import type { FeedItemOut } from "../../src/api/types";
import { freshMessages, localFeedItems, nextCall, telHref } from "../../src/connect/model";

function call(over: Partial<CallOut> = {}): CallOut {
  return {
    call_id: "call-1",
    with_person_id: "person-1",
    with_person_name: "Mei",
    with_person_phone_e164: "+6591234567",
    scheduled_at: "2026-09-19T11:30:00Z",
    call_link: null,
    label: null,
    join_words: "Ring Mei",
    added_by_person_id: "person-1",
    added_at: "2026-09-14T00:00:00Z",
    cancelled_at: null,
    ...over,
  };
}

function feedItem(over: Partial<FeedItemOut> = {}): FeedItemOut {
  return {
    item_id: "item-1",
    type: "local",
    supply: "today",
    status: "open",
    rendered_from_state: "s1",
    language: "en",
    format: "text",
    headline: "Dengue near you",
    body: ["A cluster was reported near your home."],
    voice: [],
    why: {},
    priority: 1,
    caps_class: "c",
    scope: "records",
    deliver_to: "patient",
    autoplay: false,
    source_id: null,
    ...over,
  } as FeedItemOut;
}

function entry(over: Partial<DigestEntryOut> = {}): DigestEntryOut {
  return { kind: "check_in", at: "2026-09-14T10:30:00Z", lines: ["Mei says she will bring your tablets on Sunday."], text: "I'll bring your tablets on Sunday.", message_id: "m1", ...over };
}

describe("Connect's next call (docs/design/nura-concept-board.html, the Connect screen)", () => {
  it("is the soonest call, the backend's own order, first in the list", () => {
    const soonest = call({ call_id: "soonest" });
    const later = call({ call_id: "later" });
    expect(nextCall([soonest, later])?.call_id).toBe("soonest");
  });

  it("is none when nothing is on the calendar — 'no call scheduled' is this, not a crash", () => {
    expect(nextCall([])).toBeNull();
  });
});

describe("Connect's near you: the feed's own local cards, never a stub", () => {
  it("keeps only the local cards, in the feed's order, capped at three", () => {
    const items = [feedItem({ item_id: "a", type: "local" }), feedItem({ item_id: "b", type: "reading" }), feedItem({ item_id: "c", type: "local" }), feedItem({ item_id: "d", type: "local" }), feedItem({ item_id: "e", type: "local" })];
    const kept = localFeedItems(items);
    expect(kept.map((it) => it.item_id)).toEqual(["a", "c", "d"]);
  });

  it("is empty with nothing local today — 'nothing near you yet', not a stub tile", () => {
    expect(localFeedItems([feedItem({ type: "reading" })])).toEqual([]);
  });
});

describe("Connect's messages: the digest's own freshest lines", () => {
  it("leaves out an entry with nothing to say, and caps at two", () => {
    const entries = [entry({ message_id: "1" }), entry({ message_id: "2", lines: [] }), entry({ message_id: "3" }), entry({ message_id: "4" })];
    const kept = freshMessages(entries);
    expect(kept.map((it) => it.message_id)).toEqual(["1", "3"]);
  });

  it("is empty with no messages yet", () => {
    expect(freshMessages([])).toEqual([]);
  });
});

describe("Connect's Call: the phone's own tel: over the backend's number", () => {
  it("dials exactly the number named, nothing composed here", () => {
    expect(telHref("+6591234567")).toBe("tel:+6591234567");
  });
});
