import type { JSX } from "preact";
import { Icon } from "./icons";

/** A clip's poster in a feed card (docs/ui-mockup-v2.html): the soft wash block with the play
 *  mark, and the word beside it ("Play, 20 seconds") — the whole poster is the button. Nothing
 *  plays until it is tapped. `wide`: the full-width poster under a card's lines. */
export function Poster({ label, onPlay, wide, testId }: { label: string; onPlay: () => void; wide?: boolean; testId?: string }): JSX.Element {
  return (
    <button type="button" class={wide ? "poster wide" : "poster"} onClick={onPlay} data-testid={testId ?? "poster"}>
      <span class="poster-art" aria-hidden="true">
        <Icon name="play" />
      </span>
      <span class="poster-word">{label}</span>
    </button>
  );
}
