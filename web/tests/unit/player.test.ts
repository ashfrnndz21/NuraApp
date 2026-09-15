import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { fragment, isSpeed, Player, type MediaLike, type PlayerDeps, type SpeechEvents } from "../../src/player/player";

/** The one player (E15-07): hear on tap, never by itself; Play / Pause; his speed, kept; the
 *  line being said; a clip only its stretch; a recording this key may not hear, refused. */

type FakeMedia = MediaLike & { fire(type: string): void; paused: number; played: number };

function fakeMedia(): FakeMedia {
  const listeners: Record<string, (() => void)[]> = {};
  return {
    src: "",
    currentTime: 0,
    playbackRate: 1,
    paused: 0,
    played: 0,
    play() {
      this.played += 1;
      return Promise.resolve();
    },
    pause() {
      this.paused += 1;
    },
    addEventListener(type: string, listener: () => void) {
      (listeners[type] ??= []).push(listener);
    },
    fire(type: string) {
      for (const listener of listeners[type] ?? []) listener();
    },
  };
}

function rig(overrides: Partial<PlayerDeps> = {}) {
  const media: FakeMedia[] = [];
  const said: { lines: string[]; rate: number; events: SpeechEvents }[] = [];
  const speech = {
    // The phone has a voice of its own for English only.
    say: vi.fn((lines: readonly string[], language: string, rate: number, events: SpeechEvents) => {
      if (language !== "en") return false;
      said.push({ lines: [...lines], rate, events });
      return true;
    }),
    pause: vi.fn(),
    resume: vi.fn(),
    cancel: vi.fn(),
  };
  const deps: PlayerDeps = {
    media: () => {
      const made = fakeMedia();
      media.push(made);
      return made;
    },
    objectUrl: vi.fn(() => "blob:nura/recording"),
    revoke: vi.fn(),
    fetchClip: vi.fn(async () => new Blob(["recording"], { type: "audio/webm" })),
    speech,
    saveRate: vi.fn(),
    ...overrides,
  };
  return { player: new Player(deps), deps, media, said, speech };
}

const TWIN = { kind: "speech", key: "card-1", lines: ["Your blood pressure today.", "It was 138 over 84.", "That is steady."], language: "en" } as const;
const WATER_PILL = { artifact_id: "rec-1", start_s: 19.8, end_s: 28.9 };
const clip = (key = "line-2", at = WATER_PILL) => ({ kind: "clip", key, clip: at, lines: ["Ask Dr Tan about the water pill."] }) as const;
const settle = () => new Promise((done) => setTimeout(done, 0));

describe("hear on tap, never by itself", () => {
  it("a player that is made plays nothing and shows nothing", () => {
    const { player, speech, media } = rig();
    expect(player.key.value).toBeNull();
    expect(player.status.value).toBe("idle");
    expect(speech.say).not.toHaveBeenCalled();
    expect(media).toHaveLength(0);
  });

  it("reads a card's spoken twin on the phone's own voice, the transcript following the line being said", () => {
    const { player, said } = rig();
    void player.play(TWIN);
    expect(player.key.value).toBe("card-1");
    expect(player.status.value).toBe("playing");
    expect(said[0]!.lines).toEqual(TWIN.lines);
    expect(player.line.value).toBe("Your blood pressure today.");
    said[0]!.events.onLine(1);
    expect(player.line.value).toBe("It was 138 over 84.");
  });

  it("ends and stays open with Play, so he can hear it again; the next card never starts", () => {
    const { player, said } = rig();
    void player.play(TWIN);
    said[0]!.events.onEnd();
    expect(player.status.value).toBe("idle");
    expect(player.key.value).toBe("card-1");
    expect(player.line.value).toBe("Your blood pressure today.");
    expect(said).toHaveLength(1);
    player.toggle(); // Play, after the end: from the start
    expect(said).toHaveLength(2);
    expect(said[1]!.lines).toEqual(TWIN.lines);
  });

  it("with no voice of its own on the phone for the language, says nothing and shows no player", () => {
    const { player, speech } = rig();
    void player.play({ ...TWIN, language: "ms" });
    expect(speech.say).toHaveBeenCalledTimes(1);
    expect(player.key.value).toBeNull();
    expect(player.status.value).toBe("idle");
  });

  it("one thing at a time: a new tap stops the last", async () => {
    const { player, media, speech } = rig();
    await player.play(clip());
    void player.play(TWIN);
    expect(media[0]!.paused).toBeGreaterThan(0);
    expect(speech.cancel).toHaveBeenCalled();
    expect(player.key.value).toBe("card-1");
  });

  it("leaving stops only the source that left", () => {
    const { player } = rig();
    void player.play(TWIN);
    player.leave("card-2");
    expect(player.key.value).toBe("card-1");
    player.leave("card-1");
    expect(player.key.value).toBeNull();
  });
});

describe("Play and Pause", () => {
  it("pause and go on from where it was, on the phone's voice", () => {
    const { player, speech, said } = rig();
    void player.play(TWIN);
    player.toggle();
    expect(speech.pause).toHaveBeenCalledTimes(1);
    expect(player.status.value).toBe("paused");
    player.toggle();
    expect(speech.resume).toHaveBeenCalledTimes(1);
    expect(player.status.value).toBe("playing");
    expect(said).toHaveLength(1);
  });

  it("pause and go on, on a recording", async () => {
    const { player, media } = rig();
    await player.play(clip());
    player.toggle();
    expect(media[0]!.paused).toBe(1);
    expect(player.status.value).toBe("paused");
    player.toggle();
    expect(media[0]!.played).toBe(2);
    expect(player.status.value).toBe("playing");
  });
});

describe("his speed", () => {
  it("is one of three, kept on the phone, and taken at once by what is playing", async () => {
    expect(isSpeed(0.75) && isSpeed(1) && isSpeed(1.25)).toBe(true);
    expect(isSpeed(2)).toBe(false);
    const { player, deps, media } = rig();
    await player.play(clip());
    player.setRate(0.75);
    expect(deps.saveRate).toHaveBeenCalledWith(0.75);
    expect(media[0]!.playbackRate).toBe(0.75);
    await player.play(clip("line-3"));
    expect(media[1]!.playbackRate).toBe(0.75);
  });

  it("on the phone's voice, says the rest again from the line it was on", () => {
    const { player, said, speech } = rig();
    void player.play(TWIN);
    said[0]!.events.onLine(1);
    player.setRate(1.25);
    expect(speech.cancel).toHaveBeenCalled();
    expect(said[1]).toMatchObject({ lines: TWIN.lines.slice(1), rate: 1.25 });
    // The first run, cancelled, does not report an end over the second.
    said[0]!.events.onEnd();
    expect(player.status.value).toBe("playing");
  });

  it("while paused, waits, and goes on at the new speed from the same line", () => {
    const { player, said } = rig();
    void player.play(TWIN);
    said[0]!.events.onLine(2);
    player.toggle();
    player.setRate(0.75);
    expect(said).toHaveLength(1);
    player.toggle();
    expect(said[1]).toMatchObject({ lines: [TWIN.lines[2]], rate: 0.75 });
  });
});

describe("a clip", () => {
  it("is a media fragment of the whole recording", () => {
    expect(fragment(19.8, 28.9)).toBe("#t=19.8,28.9");
    expect(fragment(10, 19.84)).toBe("#t=10,19.8");
  });

  it("plays only its stretch: from its start, paused at its end, with its line as the transcript", async () => {
    const { player, media } = rig();
    await player.play(clip());
    const audio = media[0]!;
    expect(audio.src).toBe("blob:nura/recording#t=19.8,28.9");
    expect(audio.played).toBe(1);
    expect(player.line.value).toBe("Ask Dr Tan about the water pill.");
    audio.fire("loadedmetadata");
    expect(audio.currentTime).toBe(19.8); // a fragment the element ignored is set by hand
    audio.currentTime = 24;
    audio.fire("timeupdate");
    expect(audio.paused).toBe(0);
    audio.currentTime = 28.95;
    audio.fire("timeupdate");
    expect(audio.paused).toBe(1);
    expect(player.status.value).toBe("idle");
  });

  it("fetches a recording once, warmed before the tap, and plays nothing by itself", async () => {
    const { player, deps, media } = rig();
    player.warm(WATER_PILL);
    player.warm({ ...WATER_PILL, start_s: 28.9, end_s: 36.2 });
    await settle();
    expect(deps.fetchClip).toHaveBeenCalledTimes(1);
    expect(media).toHaveLength(0);
    await player.play(clip("a"));
    await player.play(clip("b", { ...WATER_PILL, start_s: 28.9, end_s: 36.2 }));
    expect(deps.fetchClip).toHaveBeenCalledTimes(1);
    player.forget();
    await settle();
    expect(deps.revoke).toHaveBeenCalledWith("blob:nura/recording");
  });

  it("a recording this key may not hear: the refusal is kept, and no player", async () => {
    const fetchClip = vi.fn(async () => Promise.reject(new Refused("OnlyTheFamilyHears", 403)));
    const { player, media } = rig({ fetchClip });
    await player.play(clip());
    expect(player.refused.value.get("rec-1")).toBe("OnlyTheFamilyHears");
    expect(player.key.value).toBeNull();
    expect(media).toHaveLength(0);
    await player.play(clip("line-3"));
    expect(fetchClip).toHaveBeenCalledTimes(1); // not asked again
    player.forget();
    expect(player.refused.value.size).toBe(0);
  });

  it("any other failure is thrown for the screen to say, and closes the player", async () => {
    const { player } = rig({ fetchClip: vi.fn(async () => Promise.reject(new Unreachable())) });
    await expect(player.play(clip())).rejects.toBeInstanceOf(Unreachable);
    expect(player.key.value).toBeNull();
    expect(player.refused.value.size).toBe(0);
  });
});

describe("a card's pre-rendered voice", () => {
  it("plays its bytes, the card's lines as the transcript, and lets the bytes go when stopped", async () => {
    const { player, media, deps } = rig();
    await player.play({ kind: "audio", key: "card-1", blob: new Blob(["x"]), lines: ["One.", "Two."] });
    expect(media[0]!.src).toBe("blob:nura/recording");
    expect(player.line.value).toBe("One. Two.");
    media[0]!.fire("ended");
    expect(player.status.value).toBe("idle");
    player.stop();
    expect(deps.revoke).toHaveBeenCalledWith("blob:nura/recording");
    expect(player.key.value).toBeNull();
  });
});

describe("a story said in parts (E04-06)", () => {
  const parts = [
    { lines: ["This is your blood pressure tablet."], language: "en" as const, audio: null },
    { lines: ["Take 1 tablet each morning.", "Ask Dr Tan before you change anything."], language: "en" as const, audio: new Blob(["how"]) },
    { lines: ["Watch for dizziness.", "Ask Dr Tan before you change anything."], language: "en" as const, audio: null },
  ];

  it("plays the first part on the tap, stops at its end, and never starts the next by itself", () => {
    const { player, said, media } = rig();
    void player.playParts("story:line-1", parts);
    expect(said[0]!.lines).toEqual(parts[0]!.lines);
    expect(player.more.value).toBe(true);
    said[0]!.events.onEnd();
    expect(player.status.value).toBe("idle");
    expect(said).toHaveLength(1);
    expect(media).toHaveLength(0);
  });

  it("Next part plays the next, its own voice note when it has one, and Play after it says that part again", async () => {
    const { player, said, media } = rig();
    void player.playParts("story:line-1", parts);
    said[0]!.events.onEnd();
    await player.nextPart();
    expect(media).toHaveLength(1);
    expect(player.line.value).toBe("Take 1 tablet each morning. Ask Dr Tan before you change anything.");
    media[0]!.fire("ended");
    player.toggle(); // Play, after its end: the same part again, not the next
    await Promise.resolve();
    expect(media).toHaveLength(2);
    expect(said).toHaveLength(1);
    await player.nextPart();
    expect(said[1]!.lines).toEqual(parts[2]!.lines); // no voice note: the phone says its words
    expect(player.more.value).toBe(false); // the last part: no Next part
    await player.nextPart();
    expect(said).toHaveLength(2);
  });

  it("stopping, or any other tap on the player, ends the story", () => {
    const { player } = rig();
    void player.playParts("story:line-1", parts);
    void player.play({ kind: "speech", key: "hear:other", lines: ["Another card."], language: "en" });
    expect(player.more.value).toBe(false);
    void player.playParts("story:line-1", parts);
    player.stop();
    expect(player.more.value).toBe(false);
    expect(player.key.value).toBeNull();
  });
});
