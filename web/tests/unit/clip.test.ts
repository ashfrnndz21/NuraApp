import { describe, expect, it, vi } from "vitest";
import { ClipPlayer, fragment, type ClipAudio, type ClipDeps } from "../../src/visit/clip";

function player() {
  const made: (ClipAudio & { fire(type: string): void; paused: number })[] = [];
  const deps: ClipDeps = {
    fetchClip: vi.fn(async () => new Blob(["recording"], { type: "audio/webm" })),
    objectUrl: vi.fn(() => "blob:nura/recording"),
    revoke: vi.fn(),
    audio: () => {
      const listeners: Record<string, (() => void)[]> = {};
      const audio = {
        src: "",
        currentTime: 0,
        paused: 0,
        play: vi.fn(async () => undefined),
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
      made.push(audio);
      return audio;
    },
  };
  return { clips: new ClipPlayer(deps), deps, made };
}

const WATER_PILL = { artifact_id: "rec-1", start_s: 19.8, end_s: 28.9 };

describe("a clip", () => {
  it("is a media fragment of the whole recording", () => {
    expect(fragment(19.8, 28.9)).toBe("#t=19.8,28.9");
    expect(fragment(10, 19.84)).toBe("#t=10,19.8");
  });

  it("plays only its stretch, on a tap: from its start, paused at its end", async () => {
    const { clips, made } = player();
    await clips.play("line-2", WATER_PILL);
    const audio = made[0]!;
    expect(audio.src).toBe("blob:nura/recording#t=19.8,28.9");
    expect(audio.play).toHaveBeenCalledTimes(1);
    expect(clips.playing.value).toBe("line-2");
    audio.fire("loadedmetadata");
    expect(audio.currentTime).toBe(19.8); // a fragment the element ignored is set by hand
    audio.currentTime = 24;
    audio.fire("timeupdate");
    expect(audio.paused).toBe(0);
    audio.currentTime = 28.95;
    audio.fire("timeupdate");
    expect(audio.paused).toBe(1);
    expect(clips.playing.value).toBeNull();
  });

  it("fetches a recording once, warmed before the tap, and plays nothing by itself", async () => {
    const { clips, deps, made } = player();
    clips.warm(WATER_PILL);
    clips.warm({ ...WATER_PILL, start_s: 28.9, end_s: 36.2 });
    await new Promise((done) => setTimeout(done, 0));
    expect(deps.fetchClip).toHaveBeenCalledTimes(1);
    expect(made).toHaveLength(0);
    await clips.play("a", WATER_PILL);
    await clips.play("b", { ...WATER_PILL, start_s: 28.9, end_s: 36.2 });
    expect(deps.fetchClip).toHaveBeenCalledTimes(1);
    expect(made[0]!.paused).toBe(1); // the first stopped when the second was tapped
    clips.forget();
    await new Promise((done) => setTimeout(done, 0));
    expect(deps.revoke).toHaveBeenCalledWith("blob:nura/recording");
  });
});
