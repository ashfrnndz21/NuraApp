import { computed, effect, type ReadonlySignal } from "@preact/signals";
import { Refused, Unreachable } from "../api/client";
import type { Player } from "../player/player";
import type { SpokenCard } from "../speech/speak";

/** A feed card's voice, on tap and at no other time — through the one player (E15-07).
 *
 *  `hear(card)` from the Hear button's click. When the backend has the card's pre-rendered
 *  voice (E11, `GET …/feed/{item}/voice`) the player plays that; otherwise — the route is not
 *  there yet, or has nothing for this card — it reads the card's spoken twin with a voice on
 *  the phone (or stays silent). Either way it starts inside the tap, which is what a phone asks
 *  before it lets a page make a sound.
 *
 *  `warm(cards)` fetches the voices of the card on screen and the two after it, so a tap
 *  plays at once: bytes only, nothing is played. Nothing here is called when a card
 *  arrives, when the list moves, or when a voice ends; the next card never starts itself.
 *  `leave(key)` stops the voice of a card that has left the screen.
 *
 *  When a card's voice ends or is stopped, `onPlayed` is told how many seconds of it played —
 *  seconds of the voice, never of the screen (E11-08) — and whether it was played before. */

export interface PlaybackDeps {
  fetchVoice(itemId: string, language: string): Promise<Blob>;
  player: Pick<Player, "play" | "stop" | "leave" | "key" | "status">;
  /** A warm-up that was refused (not a 404): said on the screen. */
  onFailure(failure: unknown): void;
  /** The voice of this card stopped or ended: how many seconds of it played (null when the
   *  phone's own voice read it, which says nothing of how far it got), and whether this card
   *  was played before. */
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

/** A feed card's place, as the player knows it: apart from every other Hear in the app. */
const PREFIX = "feed:";

export class Playback {
  /** The place of the card whose voice is open in the player, or null. */
  readonly playing: ReadonlySignal<string | null>;
  /** The backend has no voice route at all (its 404 was not a refusal): stop asking. */
  routeAbsent = false;
  private readonly ready = new Map<string, Voice>();
  private readonly asking = new Set<string>();
  /** The card whose voice was asked for last: when it started (null: the phone's own voice),
   *  and whether the player has it under way yet — a voice that never started is no play. */
  private started: { key: string; itemId: string; at: number | null; live: boolean } | null = null;
  private readonly heardBefore = new Set<string>();
  private readonly unwatch: () => void;

  constructor(private readonly deps: PlaybackDeps) {
    this.playing = computed(() => {
      const key = deps.player.key.value;
      return key?.startsWith(PREFIX) ? key.slice(PREFIX.length) : null;
    });
    // The player says when a card's voice is under way, and when it has ended (idle on its
    // place) or stopped (its place let go: Stop, another tap, the card off the screen).
    this.unwatch = effect(() => {
      const key = deps.player.key.value;
      const status = deps.player.status.value;
      const card = this.started;
      if (!card) return;
      const ours = key === PREFIX + card.key;
      if (ours && (status === "playing" || status === "loading")) card.live = true;
      else if (card.live && (!ours || status === "idle")) this.played();
    });
  }

  private clock(): number {
    return this.deps.clock ? this.deps.clock() : performance.now();
  }

  /** The voice that was under way has ended or stopped: say how much of it played, once. */
  private played(): void {
    const was = this.started;
    this.started = null;
    if (!was?.live) return;
    const seconds = was.at === null ? null : Math.max(0, (this.clock() - was.at) / 1000);
    const again = this.heardBefore.has(was.itemId);
    this.heardBefore.add(was.itemId);
    this.deps.onPlayed?.(was.itemId, seconds, again);
  }

  /** Stop listening to the player: the feed is gone. */
  dispose(): void {
    this.unwatch();
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
    const key = PREFIX + card.key;
    const twin = { kind: "speech", key, lines: card.lines, language: card.language } as const;
    const voice = this.ready.get(card.itemId);
    if (this.started) this.played();
    this.started = { key: card.key, itemId: card.itemId, at: voice?.kind === "audio" ? this.clock() : null, live: false };
    if (voice?.kind === "audio") {
      // The phone would not play the bytes: read the spoken twin instead, still in the tap.
      this.deps.player.play({ kind: "audio", key, blob: voice.blob, lines: card.lines }).catch(() => {
        if (this.started?.itemId === card.itemId) this.started.at = null;
        return this.deps.player.play(twin).catch(() => undefined);
      });
      return;
    }
    void this.deps.player.play(twin).catch(() => undefined);
  }

  /** The card at `key` has left the screen: its voice stops. Any other card's plays on. */
  leave(key: string): void {
    this.deps.player.leave(PREFIX + key);
  }

  /** Stop a feed card's voice, if one is open; anything else the player holds is left alone. */
  stop(): void {
    if (this.playing.peek() !== null) this.deps.player.stop();
  }
}

/** An audio element as the Record's story voice (W5, `record/storyVoice.ts`) plays it: a part of
 *  a medicine's story, on a tap. Kept for that screen; the feed's cards play through the one
 *  player (E15-07) above. */
export interface AudioLike {
  play(): Promise<void>;
  pause(): void;
  onended: (() => void) | null;
}

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
