import { describe, expect, it } from "vitest";
import type { AudioLike } from "../../src/feed/playback";
import { StoryVoice } from "../../src/record/storyVoice";
import type { SpokenCard } from "../../src/speech/speak";

function world(options: { missing?: string[]; unplayable?: boolean } = {}) {
  const fetched: string[] = [];
  const played: string[] = [];
  const stopped: string[] = [];
  const spoken: SpokenCard[] = [];
  const voice = new StoryVoice({
    fetch: async (part) => {
      fetched.push(part);
      if (options.missing?.includes(part)) throw new Error("NotFound");
      return new Blob([part]);
    },
    audio: (blob): AudioLike => {
      const name = String((blob as Blob & { size: number }).size);
      const audio: AudioLike = {
        play: async () => {
          if (options.unplayable) throw new Error("NotAllowedError");
          played.push(name);
        },
        pause: () => {
          stopped.push(name);
        },
        onended: null,
      };
      return audio;
    },
    speak: (card) => spoken.push(card),
  });
  return { voice, fetched, played, stopped, spoken };
}

const lines = (words: string): SpokenCard => ({ lines: [words], language: "en" });

describe("the story's voice notes", () => {
  it("fetches each part's note when the story opens and plays nothing until a tap", async () => {
    const { voice, fetched, played, spoken } = world();
    voice.warm(["purpose", "how_to_take"]);
    await Promise.resolve();
    expect(fetched).toEqual(["purpose", "how_to_take"]);
    expect(played).toEqual([]);
    expect(spoken).toEqual([]);
  });

  it("plays the backend's note for the part tapped, fetched once", async () => {
    const { voice, fetched, played, spoken } = world();
    voice.warm(["purpose"]);
    expect(await voice.hear("purpose", lines("It keeps your blood pressure down."))).toBe("voice");
    expect(fetched).toEqual(["purpose"]);
    expect(played).toHaveLength(1);
    expect(spoken).toEqual([]);
  });

  it("says the part's own lines in the phone's voice when the backend has no note for it", async () => {
    const { voice, played, spoken } = world({ missing: ["avoid"] });
    expect(await voice.hear("avoid", lines("Stay away from grapefruit."))).toBe("phone");
    expect(played).toEqual([]);
    expect(spoken).toEqual([lines("Stay away from grapefruit.")]);
  });

  it("says the lines when the phone will not play the note", async () => {
    const { voice, spoken, stopped } = world({ unplayable: true });
    expect(await voice.hear("purpose", lines("It keeps your blood pressure down."))).toBe("phone");
    expect(spoken).toHaveLength(1);
    expect(stopped).toHaveLength(1);
  });

  it("stops what was playing when another part is heard, and on leaving", async () => {
    const { voice, stopped } = world();
    await voice.hear("purpose", lines("a"));
    await voice.hear("how_to_take", lines("b"));
    expect(stopped).toHaveLength(1);
    voice.stop();
    expect(stopped).toHaveLength(2);
  });
});
