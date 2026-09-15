import { describe, expect, it } from "vitest";
import type { StoryOut } from "../../src/api/types";
import { storyParts } from "../../src/player/story";

/** The medication story as the player says it (E04-06): one part per voice note, in the
 *  backend's order; every part but what it is for ends on the boundary. */

const STORY: StoryOut = {
  line_id: "l1",
  language: "en",
  name: "your blood pressure tablet",
  generic: "amlodipine",
  strength: "5 mg",
  purpose: ["This is your blood pressure tablet."],
  how_to_take: ["Take 1 tablet each morning."],
  watch_out: ["Swollen ankles can happen."],
  avoid: [],
  if_forgotten: ["If you forgot, leave it."],
  boundary: ["Ask Dr Tan before you change anything."],
  doctor_question: [],
  lines: [],
  voice_parts: ["purpose", "how_to_take", "watch_out", "if_forgotten"],
};

describe("the story's parts", () => {
  it("follow the backend's order, each with its voice note or none, the boundary after every part but the first", () => {
    const note = new Blob(["how"]);
    const parts = storyParts(STORY, "en", new Map([["how_to_take", note], ["watch_out", null]]));
    expect(parts.map((part) => part.lines)).toEqual([
      ["This is your blood pressure tablet."],
      ["Take 1 tablet each morning.", "Ask Dr Tan before you change anything."],
      ["Swollen ankles can happen.", "Ask Dr Tan before you change anything."],
      ["If you forgot, leave it.", "Ask Dr Tan before you change anything."],
    ]);
    expect(parts.map((part) => part.audio)).toEqual([null, note, null, null]);
  });

  it("leave out a part the backend did not voice, and any it does not know", () => {
    const parts = storyParts({ ...STORY, voice_parts: ["purpose", "something_new"] }, "en", new Map());
    expect(parts).toHaveLength(1);
  });
});
