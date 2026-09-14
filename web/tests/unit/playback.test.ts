import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { Playback, type AudioLike, type PlaybackDeps } from "../../src/feed/playback";
import { FeedStore } from "../../src/feed/store";
import { item, page } from "./feedFixtures";

function player(overrides: Partial<PlaybackDeps> = {}) {
  const played: AudioLike[] = [];
  const deps: PlaybackDeps = {
    fetchVoice: vi.fn(async () => Promise.reject(new Refused("NotFound", 404))),
    speak: vi.fn(),
    stopSpeaking: vi.fn(),
    audio: vi.fn(() => {
      const audio: AudioLike = { play: vi.fn(async () => undefined), pause: vi.fn(), onended: null };
      played.push(audio);
      return audio;
    }),
    onFailure: vi.fn(),
    ...overrides,
  };
  return { playback: new Playback(deps), deps, played };
}

const card = (key: string, itemId = key) => ({ key, itemId, lines: [`${itemId} one.`, `${itemId} two.`], language: "en" as const });
const settle = () => new Promise((done) => setTimeout(done, 0));

describe("no autoplay", () => {
  it("paging through the whole feed plays nothing: no voice starts without a tap", async () => {
    const { playback, deps } = player();
    const pages = (n: number) => page([item("story", "story"), item("learning", "learning"), item("story", "story")], `c${n}`, `c${n + 1}`);
    const feed = new FeedStore({
      first: async () => page([item("now", "now"), item("reading", "today"), item("gate", "gate")], null, "c1"),
      next: async (cursor) => pages(Number(cursor.slice(1))),
      cached: async () => Promise.reject(new Refused("NoCachedPage", 404)),
      keep: { load: async () => null, save: async (p) => ({ page: p, binding: { keyId: "owner", scopes: [] }, fetchedAt: "", expiresAt: "" }), clear: async () => undefined },
      engage: async () => ({}),
      share: async () => ({}),
      canEngage: true,
      now: () => new Date("2026-09-14T02:00:00Z"),
    });
    await feed.open();
    for (let at = 0; at < 25; at++) {
      await feed.visible(at);
      const list = feed.entries.value;
      // What the pager does as each card arrives: warm the voices around it, and nothing else.
      playback.warm(list.slice(at, at + 3).map((entry) => ({ itemId: entry.item.item_id, language: entry.item.language })));
      for (const entry of list) expect(entry.item.autoplay).toBe(false);
    }
    await settle();
    expect(deps.speak).not.toHaveBeenCalled();
    expect(deps.audio).not.toHaveBeenCalled();
    expect(playback.playing.value).toBeNull();
  });

  it("a voice that ends does not start the next card's", async () => {
    const blob = new Blob(["x"], { type: "audio/mpeg" });
    const { playback, deps, played } = player({ fetchVoice: vi.fn(async () => blob) });
    playback.warm([{ itemId: "a", language: "en" }, { itemId: "b", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    played[0]!.onended?.();
    await settle();
    expect(deps.audio).toHaveBeenCalledTimes(1);
    expect(deps.speak).not.toHaveBeenCalled();
    expect(playback.playing.value).toBeNull();
  });
});

describe("hear on tap", () => {
  it("reads the spoken twin once through the phone's voice when the backend has no voice route", async () => {
    const { playback, deps } = player();
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    expect(playback.routeAbsent).toBe(true);
    playback.hear(card("0:0", "a"));
    expect(deps.speak).toHaveBeenCalledTimes(1);
    expect(deps.speak).toHaveBeenCalledWith(expect.objectContaining({ lines: ["a one.", "a two."], language: "en" }));
    expect(playback.playing.value).toBe("0:0");
  });

  it("stops asking for voices once the route is known to be absent", async () => {
    const { playback, deps } = player();
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    playback.warm([{ itemId: "b", language: "en" }, { itemId: "c", language: "en" }]);
    await settle();
    expect(deps.fetchVoice).toHaveBeenCalledTimes(1);
  });

  it("plays the backend's pre-rendered voice when it has one, and not the phone's", async () => {
    const blob = new Blob(["x"], { type: "audio/mpeg" });
    const { playback, deps, played } = player({ fetchVoice: vi.fn(async () => blob) });
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    expect(deps.audio).toHaveBeenCalledWith(blob);
    expect(played[0]!.play).toHaveBeenCalledTimes(1);
    expect(deps.speak).not.toHaveBeenCalled();
  });

  it("falls back to the spoken twin for a card the backend has no voice for (a refusal 404), and keeps asking for others", async () => {
    const fetchVoice = vi.fn(async (id: string) => (id === "a" ? Promise.reject(new Refused("NoVoiceYet", 404)) : new Blob(["x"])));
    const { playback, deps } = player({ fetchVoice });
    playback.warm([{ itemId: "a", language: "en" }, { itemId: "b", language: "en" }]);
    await settle();
    expect(playback.routeAbsent).toBe(false);
    playback.hear(card("0:0", "a"));
    expect(deps.speak).toHaveBeenCalledTimes(1);
    playback.hear(card("0:1", "b"));
    expect(deps.audio).toHaveBeenCalledTimes(1);
  });

  it("says a refused voice rather than swallow it", async () => {
    const refusal = new Refused("OutOfScope", 403, "records");
    const { playback, deps } = player({ fetchVoice: vi.fn(async () => Promise.reject(refusal)) });
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    expect(deps.onFailure).toHaveBeenCalledWith(refusal);
  });

  it("asks again after the network comes back", async () => {
    const fetchVoice = vi.fn(async () => Promise.reject(new Unreachable()));
    const { playback } = player({ fetchVoice });
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    expect(fetchVoice).toHaveBeenCalledTimes(2);
  });
});

describe("leaving the screen", () => {
  it("stops the voice of the card that left, and only that card's", () => {
    const { playback, deps } = player();
    playback.hear(card("0:1"));
    playback.leave("0:0");
    expect(playback.playing.value).toBe("0:1");
    playback.leave("0:1");
    expect(playback.playing.value).toBeNull();
    expect(deps.stopSpeaking).toHaveBeenCalledTimes(2); // once before it started, once when it left
  });

  it("a new tap stops the voice before", async () => {
    const blob = new Blob(["x"]);
    const { playback, played } = player({ fetchVoice: vi.fn(async () => blob) });
    playback.warm([{ itemId: "a", language: "en" }, { itemId: "b", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    playback.hear(card("0:1", "b"));
    expect(played[0]!.pause).toHaveBeenCalled();
    expect(playback.playing.value).toBe("0:1");
  });
});
