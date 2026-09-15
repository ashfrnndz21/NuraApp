import type { StoryOut } from "../api/types";
import type { Language } from "../strings";
import type { Part } from "./player";

/** The medication story as the one player says it (E04-06): one part per voice note, in the
 *  backend's order (`voice_parts`). A part's words are its section's lines, and every part but
 *  what it is for ends on the story's boundary, as its voice note does — each plays on its own
 *  tap. `audio` is the part's voice note where the backend has one; without it the phone says
 *  those same words. Pure, so it is unit-tested. */

const SECTIONS = ["purpose", "how_to_take", "watch_out", "avoid", "if_forgotten"] as const;
type Section = (typeof SECTIONS)[number];

function isSection(part: string): part is Section {
  return (SECTIONS as readonly string[]).includes(part);
}

export function storyParts(story: StoryOut, language: Language, audio: ReadonlyMap<string, Blob | null>): Part[] {
  return (story.voice_parts ?? []).filter(isSection).map((part) => ({
    lines: part === "purpose" ? [...story[part]] : [...story[part], ...story.boundary],
    language,
    audio: audio.get(part) ?? null,
  }));
}
