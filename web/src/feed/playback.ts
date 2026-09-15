import { signal } from "@preact/signals";
import { Refused, Unreachable } from "../api/client";
import type { SpokenCard } from "../speech/speak";

/** A card's voice, on tap and at no other time.
 *
 *  One seam: `hear(card)` from the Hear button's click. When the backend has the card's
 *  pre-rendered voice (E11, `GET …/feed/{item}/voice`) it plays that; otherwise — the route
 *  is not there yet, or has nothing for this card — it reads the card's spoken twin through
 *  W1's `speak()` (a voice on the phone only, or silence). Either way it starts inside the
 *  tap, which is what a phone asks before it lets a page make a sound.
 *
 *  `warm(cards)` fetches the voices of the card on screen and the two after it, so a tap
 *  plays at once: bytes only, nothing is played. Nothing here is called when a card
 *  arrives, when the list moves, or when a voice ends; the next card never starts itself.
 *  `leave(key)` stops the voice of a card that has left the screen. */

export interface AudioLike {
  play(): Promise<void>;
  pause(): void;
  onended: (() => void) | null;
}

export interface PlaybackDeps {
  fetchVoice(itemId: string, language: string): Promise<Blob>;
  speak(card: SpokenCard): void;
  stopSpeaking(): void;
  audio(blob: Blob): AudioLike;
  /** A warm-up that was refused (not a 404): said on the screen. */
  onFailure(failure: unknown): void;
  /** The voice of this card stopped or ended: how many seconds of it played (null when the
   *  phone's own voice read it, which says nothing of how far it got), and whether this card
   *  was played before. Seconds of the voice, never of the screen (E11-08). */
  onPlayed?(itemId: string, seconds: number | null, again: boolean): void;
  /** The clock the seconds are read on; the page's own by default. */
  clock?(): number;
}

export interface HearCard extends SpokenCard {
  /** The card's place in the list: what `leave` is told when it scrolls away. */
  key: string;
  itemId: string;
}

type Voice = { kind: "audio"; blob: Blob } | { kind: "none" };

export class Playback {
  /** The place of the card whose voice is playing, or null. */
  readonly playing = signal<string | null>(null);
  /** The backend has no voice route at all (its 404 was not a refusal): stop asking. */
  routeAbsent = false;
  private readonly ready = new Map<string, Voice>();
  private readonly asking = new Set<string>();
  private current: AudioLike | null = null;
  /** The card whose voice is playing, and when it started (null seconds: the phone's voice). */
  private started: { itemId: string; at: number | null } | null = null;
  private readonly heardBefore = new Set<string>();

  constructor(private readonly deps: PlaybackDeps) {}

  private clock(): number {
    return this.deps.clock ? this.deps.clock() : performance.now();
  }

  /** The voice that was playing has stopped or ended: say how much of it played, once. */
  private played(): void {
    const was = this.started;
    this.started = null;
    if (!was) return;
    const seconds = was.at === null ? null : Math.max(0, (this.clock() - was.at) / 1000);
    const again = this.heardBefore.has(was.itemId);
    this.heardBefore.add(was.itemId);
    this.deps.onPlayed?.(was.itemId, seconds, again);
  }

  /** Fetch, never play, the voices of these cards. */
  warm(cards: readonly { itemId: string; language: string }[]): void {
    for (const card of cards) {
      if (this.routeAbsent) return;
      if (this.ready.has(card.itemId) || this.asking.has(card.itemId)) continue;
      this.asking.add(card.itemId);
      this.deps
        .fetchVoice(card.itemId, card.language)
        .then((blob) => this.ready.set(card.itemId, { kind: "audio", blob }))
        .catch((failure: unknown) => {
          if (failure instanceof Refused && failure.status === 404) {
            // No route (a plain 404), or no voice for this card (a refusal): the spoken twin.
            if (failure.refusal === "NotFound") this.routeAbsent = true;
            this.ready.set(card.itemId, { kind: "none" });
          } else if (!(failure instanceof Unreachable)) {
            this.ready.set(card.itemId, { kind: "none" });
            this.deps.onFailure(failure);
          }
        })
        .finally(() => this.asking.delete(card.itemId));
    }
  }

  /** Read this card out. Call from a tap and from nowhere else. */
  hear(card: HearCard): void {
    this.stop();
    this.playing.value = card.key;
    const voice = this.ready.get(card.itemId);
    if (voice?.kind === "audio") {
      const audio = this.deps.audio(voice.blob);
      this.current = audio;
      this.started = { itemId: card.itemId, at: this.clock() };
      audio.onended = () => this.finished(card.key);
      audio.play().catch(() => {
        // The phone would not play the bytes: read the spoken twin instead, still in the tap.
        this.current = null;
        this.started = { itemId: card.itemId, at: null };
        this.deps.speak(card);
      });
      return;
    }
    this.started = { itemId: card.itemId, at: null };
    this.deps.speak(card);
  }

  /** The card at `key` has left the screen: its voice stops. Any other card's plays on. */
  leave(key: string): void {
    if (this.playing.value === key) this.stop();
  }

  stop(): void {
    this.current?.pause();
    this.current = null;
    this.deps.stopSpeaking();
    this.playing.value = null;
    this.played();
  }

  private finished(key: string): void {
    if (this.playing.value === key) {
      this.current = null;
      this.playing.value = null;
      this.played();
    }
  }
}

/** The browser's audio element for a blob of pre-rendered voice. */
export function browserAudio(blob: Blob): AudioLike {
  const url = URL.createObjectURL(blob);
  const element = new Audio(url);
  const audio: AudioLike = {
    play: () => element.play(),
    pause: () => {
      element.pause();
      URL.revokeObjectURL(url);
    },
    onended: null,
  };
  element.onended = () => {
    URL.revokeObjectURL(url);
    audio.onended?.();
  };
  return audio;
}
