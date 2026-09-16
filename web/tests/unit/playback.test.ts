import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { Playback, type PlaybackDeps } from "../../src/feed/playback";
import { FeedStore } from "../../src/feed/store";
import { Player, type MediaLike, type PlayerDeps } from "../../src/player/player";
import { item, page } from "./feedFixtures";

/** The feed's voice goes through the one player (E15-07), with a stand-in for the phone's
 *  voice and for the audio element. */
function player(overrides: Partial<PlaybackDeps> = {}, playerOverrides: Partial<PlayerDeps> = {}) {
  const played: (MediaLike & { paused: number })[] = [];
  const speech = { say: vi.fn(() => true), pause: vi.fn(), resume: vi.fn(), cancel: vi.fn() };
  const media = vi.fn(() => {
    const made = {
      src: "",
      currentTime: 0,
      playbackRate: 1,
      paused: 0,
      play: vi.fn(async () => undefined),
      pause() {
        this.paused += 1;
      },
      addEventListener: vi.fn(),
    };
    played.push(made);
    return made;
  });
  const voice = new Player({
    media,
    objectUrl: vi.fn(() => "blob:nura/voice"),
    revoke: vi.fn(),
    fetchClip: vi.fn(),
    speech,
    saveRate: vi.fn(),
    ...playerOverrides,
  });
  const deps: PlaybackDeps = {
    fetchVoice: vi.fn(async () => Promise.reject(new Refused("NotFound", 404))),
    player: voice,
    onFailure: vi.fn(),
    ...overrides,
  };
  return { playback: new Playback(deps), deps, voice, speech, media, played };
}

const card = (key: string, itemId = key) => ({ key, itemId, lines: [`${itemId} one.`, `${itemId} two.`], language: "en" as const });
const settle = () => new Promise((done) => setTimeout(done, 0));

describe("no autoplay", () => {
  it("paging through the whole feed plays nothing: no voice starts without a tap", async () => {
    const { playback, speech, media } = player();
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
    expect(speech.say).not.toHaveBeenCalled();
    expect(media).not.toHaveBeenCalled();
    expect(playback.playing.value).toBeNull();
  });

  it("a voice that ends does not start the next card's", async () => {
    const blob = new Blob(["x"], { type: "audio/mpeg" });
    const ended: (() => void)[] = [];
    const { playback, speech, media } = player({ fetchVoice: vi.fn(async () => blob) });
    playback.warm([{ itemId: "a", language: "en" }, { itemId: "b", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    const made = media.mock.results[0]!.value as { addEventListener: ReturnType<typeof vi.fn> };
    for (const [type, listener] of made.addEventListener.mock.calls as [string, () => void][]) if (type === "ended") ended.push(listener);
    for (const listener of ended) listener();
    await settle();
    expect(media).toHaveBeenCalledTimes(1);
    expect(speech.say).not.toHaveBeenCalled();
  });
});

describe("hear on tap", () => {
  it("reads the spoken twin once through the phone's voice when the backend has no voice route", async () => {
    const { playback, speech } = player();
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    expect(playback.routeAbsent).toBe(true);
    playback.hear(card("0:0", "a"));
    expect(speech.say).toHaveBeenCalledTimes(1);
    expect(speech.say).toHaveBeenCalledWith(["a one.", "a two."], "en", 1, expect.anything());
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
    const { playback, speech, played, voice } = player({ fetchVoice: vi.fn(async () => blob) });
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    await settle();
    expect(played[0]!.src).toBe("blob:nura/voice");
    expect(played[0]!.play).toHaveBeenCalledTimes(1);
    expect(speech.say).not.toHaveBeenCalled();
    expect(voice.line.value).toBe("a one. a two.");
  });

  it("reads the spoken twin, still in the tap, when the phone will not play the bytes", async () => {
    const blob = new Blob(["x"], { type: "audio/mpeg" });
    const refusing = {
      media: () => ({ src: "", currentTime: 0, playbackRate: 1, play: () => Promise.reject(new Error("NotAllowedError")), pause: () => undefined, addEventListener: () => undefined }),
    };
    const { playback, speech } = player({ fetchVoice: vi.fn(async () => blob) }, refusing);
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    await settle();
    expect(speech.say).toHaveBeenCalledTimes(1);
    expect(playback.playing.value).toBe("0:0");
  });

  it("falls back to the spoken twin for a card the backend has no voice for (a refusal 404), and keeps asking for others", async () => {
    const fetchVoice = vi.fn(async (id: string) => (id === "a" ? Promise.reject(new Refused("NoVoiceYet", 404)) : new Blob(["x"])));
    const { playback, speech, media } = player({ fetchVoice });
    playback.warm([{ itemId: "a", language: "en" }, { itemId: "b", language: "en" }]);
    await settle();
    expect(playback.routeAbsent).toBe(false);
    playback.hear(card("0:0", "a"));
    expect(speech.say).toHaveBeenCalledTimes(1);
    playback.hear(card("0:1", "b"));
    expect(media).toHaveBeenCalledTimes(1);
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
    const { playback, speech } = player();
    playback.hear(card("0:1"));
    playback.leave("0:0");
    expect(playback.playing.value).toBe("0:1");
    const before = speech.cancel.mock.calls.length;
    playback.leave("0:1");
    expect(playback.playing.value).toBeNull();
    expect(speech.cancel.mock.calls.length).toBe(before + 1);
  });

  it("a new tap stops the voice before", async () => {
    const blob = new Blob(["x"]);
    const { playback, played } = player({ fetchVoice: vi.fn(async () => blob) });
    playback.warm([{ itemId: "a", language: "en" }, { itemId: "b", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    playback.hear(card("0:1", "b"));
    expect(played[0]!.paused).toBeGreaterThan(0);
    expect(playback.playing.value).toBe("0:1");
  });

  it("stopping the feed leaves any other voice in the app alone", () => {
    const { playback, voice } = player();
    void voice.play({ kind: "speech", key: "hear:today", lines: ["Your day is steady."], language: "en" });
    playback.stop();
    expect(voice.key.value).toBe("hear:today");
    playback.hear(card("0:0"));
    playback.stop();
    expect(voice.key.value).toBeNull();
  });
});

describe("how much played (E11-08)", () => {
  it("the phone's voice ending is a play with no seconds, and the next play of the card is a replay", async () => {
    const onPlayed = vi.fn();
    const { playback, speech } = player({ onPlayed });
    playback.warm([{ itemId: "a", language: "en" }]);
    await settle();
    playback.hear(card("0:0", "a"));
    await settle();
    const ended = () => (speech.say.mock.calls.at(-1) as unknown as [unknown, unknown, unknown, { onEnd(): void }])[3].onEnd();
    ended();
    expect(onPlayed.mock.calls).toEqual([["a", null, false]]);
    playback.hear(card("0:0", "a"));
    await settle();
    ended();
    expect(onPlayed.mock.calls.at(-1)).toEqual(["a", null, true]);
  });

  it("Stop on the backend's voice says the seconds of the voice that played, once", async () => {
    const onPlayed = vi.fn();
    let now = 1_000;
    const { playback } = player({ onPlayed, clock: () => now, fetchVoice: vi.fn(async () => new Blob(["voice"])) });
    playback.warm([{ itemId: "b", language: "en" }]);
    await settle();
    playback.hear(card("0:1", "b"));
    await settle();
    now = 4_500;
    playback.stop();
    playback.stop();
    expect(onPlayed.mock.calls).toEqual([["b", 3.5, false]]);
  });

  it("a voice that never started is no play", async () => {
    const onPlayed = vi.fn();
    const { playback } = player({ onPlayed }, { speech: { say: vi.fn(() => false), pause: vi.fn(), resume: vi.fn(), cancel: vi.fn() } });
    playback.hear(card("0:2", "c"));
    await settle();
    playback.stop();
    expect(onPlayed).not.toHaveBeenCalled();
  });
});
