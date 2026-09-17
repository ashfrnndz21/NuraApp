import { signal } from "@preact/signals";
import type { AudioLike } from "../feed/playback";
import type { SpokenCard } from "../speech/speak";

/** What the story's voice needs from the world, so it is tested without a browser. */
export interface StoryVoiceDeps {
  /** One part's voice note from the backend (`…/medicines/{line}/story/voice?part=`). */
  fetch: (part: string) => Promise<Blob>;
  audio: (blob: Blob) => AudioLike;
  /** The phone's own voice, for a part the backend has no note for. `onEnd`, when the phone
   *  actually said the words (it is not called when there was no voice to say them with),
   *  is how `speaking` clears itself once this part stops sounding. */
  speak: (card: SpokenCard, onEnd?: () => void) => void;
}

/** The medicine story's voice notes (E04-06): one a part, played on a tap and never by
 *  themselves. When the story opens each part's note is fetched — never played — so the tap
 *  plays it at once, inside the tap, the way the feed's voices are warmed. A part the backend
 *  has no note for (a plain 404: nothing to say, no voice in the language yet, or too long),
 *  or bytes the phone will not play, is said from the part's own lines in the phone's voice. */
export class StoryVoice {
  private readonly kept = new Map<string, Promise<Blob | null>>();
  private playing: AudioLike | null = null;
  private asked = 0;

  /** The part actually sounding now (the backend's note playing, or the phone mid-sentence),
   *  or null. Drives the brand mark's "speaking" motion (docs/brand/BRAND.md §7) on that
   *  part's Hear button; every other part's stays idle. */
  readonly speaking = signal<string | null>(null);

  constructor(private readonly deps: StoryVoiceDeps) {}

  /** Fetch, never play, these parts' notes. */
  warm(parts: readonly string[]): void {
    for (const part of parts) this.note(part);
  }

  private note(part: string): Promise<Blob | null> {
    let found = this.kept.get(part);
    if (!found) {
      found = this.deps.fetch(part).catch(() => null);
      this.kept.set(part, found);
    }
    return found;
  }

  /** His tap on one part's Hear: the backend's note, or the part's lines in the phone's voice.
   *  Whatever was playing stops first; a tap on another part while this one is fetched wins. */
  async hear(part: string, fallback: SpokenCard): Promise<"voice" | "phone" | "superseded"> {
    this.stop();
    const ticket = ++this.asked;
    if (ticket === this.asked) this.speaking.value = part;
    const blob = await this.note(part);
    if (ticket !== this.asked) return "superseded";
    if (blob) {
      const audio = this.deps.audio(blob);
      this.playing = audio;
      audio.onended = () => {
        if (ticket === this.asked) this.speaking.value = null;
      };
      try {
        await audio.play();
        return "voice";
      } catch {
        if (ticket !== this.asked) return "superseded";
        audio.pause();
        this.playing = null;
      }
    }
    this.deps.speak(fallback, () => {
      if (ticket === this.asked) this.speaking.value = null;
    });
    return "phone";
  }

  stop(): void {
    this.asked++; // an onended or onEnd still in flight for the old ticket is now a no-op
    this.playing?.pause();
    this.playing = null;
    this.speaking.value = null;
  }
}
