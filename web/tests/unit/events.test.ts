import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import type { EventsOut, QueuedEventIn } from "../../src/api/types";
import { EventQueue, FLUSH_LIMIT, type EventQueueDeps } from "../../src/feed/events";

const NOW = new Date("2026-09-14T02:00:00Z");

function queue(send: EventQueueDeps["send"] = async (list) => ({ written: list.map((one) => one.client_id), skipped: [] })) {
  let kept: QueuedEventIn[] = [];
  let n = 0;
  const deps: EventQueueDeps = {
    load: vi.fn(async () => kept),
    save: vi.fn(async (list: QueuedEventIn[]) => {
      kept = list;
    }),
    send: vi.fn(send),
    now: () => NOW,
    id: () => `id-${++n}`,
  };
  return { events: new EventQueue(deps), deps, kept: () => kept };
}

describe("the queue of what he did with his cards (E11-08)", () => {
  it("keeps each event with its own id, the card, what, and when", async () => {
    const { events, kept } = queue();
    await events.add("card-1", "opened");
    await events.add("card-1", "played", 12.345);
    expect(kept()).toEqual([
      { client_id: "id-1", item_id: "card-1", event: "opened", at: NOW.toISOString(), channel: "app", seconds: null },
      { client_id: "id-2", item_id: "card-1", event: "played", at: NOW.toISOString(), channel: "app", seconds: 12.3 },
    ]);
  });

  it("sends what it kept on the next connection and forgets it once answered, written or skipped", async () => {
    const { events, deps, kept } = queue(async (list) => ({ written: list.slice(0, 1).map((one) => one.client_id), skipped: list.slice(1).map((one) => ({ client_id: one.client_id, because: "already_written" })) }));
    await events.add("a", "opened");
    await events.add("b", "asked_more");
    await events.flush();
    expect(deps.send).toHaveBeenCalledTimes(1);
    expect(kept()).toEqual([]);
  });

  it("keeps the queue when the network is lost, and sends it next time", async () => {
    let online = false;
    const { events, deps, kept } = queue(async (list): Promise<EventsOut> => {
      if (!online) throw new Unreachable();
      return { written: list.map((one) => one.client_id), skipped: [] };
    });
    await events.add("a", "shared");
    await events.flush();
    expect(kept()).toHaveLength(1);
    online = true;
    await events.flush();
    expect(kept()).toEqual([]);
    expect(deps.send).toHaveBeenCalledTimes(2);
  });

  it("forgets a batch the backend refused: a no is not asked again", async () => {
    const { events, kept } = queue(async () => {
      throw new Refused("OutOfScope", 403);
    });
    await events.add("a", "opened");
    await events.flush();
    expect(kept()).toEqual([]);
  });

  it("sends at most the backend's limit at a time", async () => {
    const { events, deps } = queue();
    for (let i = 0; i < FLUSH_LIMIT + 5; i++) await events.add(`card-${i}`, "opened");
    await events.flush();
    expect(vi.mocked(deps.send).mock.calls.map(([list]) => list.length)).toEqual([FLUSH_LIMIT, 5]);
  });
});

describe("never time in the feed", () => {
  it("carries seconds only on a play or a replay — never on opened, asked more or shared", async () => {
    const { events, kept } = queue();
    // A caller that tries to say how long a card was on screen is ignored: opened is once, or not.
    await events.add("a", "opened", 45);
    await events.add("a", "asked_more", 30);
    await events.add("a", "shared", 10);
    await events.add("a", "replayed", 8);
    expect(kept().map((one) => [one.event, one.seconds])).toEqual([
      ["opened", null],
      ["asked_more", null],
      ["shared", null],
      ["replayed", 8],
    ]);
  });

  it("has no kind of event that measures the screen", () => {
    // The only kinds the phone can queue: none of them is a dwell, a view time or a session.
    const kinds: Parameters<EventQueue["add"]>[1][] = ["opened", "played", "replayed", "asked_more", "shared"];
    for (const kind of kinds) expect(kind).not.toMatch(/dwell|view|time|session|scroll|duration/);
  });

  it("says a play is never longer than the backend accepts, and never less than nothing", async () => {
    const { events, kept } = queue();
    await events.add("a", "played", 9999);
    await events.add("a", "played", -3);
    expect(kept().map((one) => one.seconds)).toEqual([600, 0]);
  });
});
