import { computed, type ReadonlySignal } from "@preact/signals";
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
 *  `leave(key)` stops the voice of a card that has left the screen. */

export interface PlaybackDeps {
  fetchVoice(itemId: string, language: string): Promise<Blob>;
  player: Pick<Player, "play" | "stop" | "leave" | "key">;
  /** A warm-up that was refused (not a 404): said on the screen. */
  onFailure(failure: unknown): void;
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

  constructor(private readonly deps: PlaybackDeps) {
    this.playing = computed(() => {
      const key = deps.player.key.value;
      return key?.startsWith(PREFIX) ? key.slice(PREFIX.length) : null;
    });
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
    if (voice?.kind === "audio") {
      // The phone would not play the bytes: read the spoken twin instead, still in the tap.
      this.deps.player.play({ kind: "audio", key, blob: voice.blob, lines: card.lines }).catch(() => this.deps.player.play(twin).catch(() => undefined));
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
