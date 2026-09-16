import type { JSX } from "preact";

/** Good, Watch, Act — the three state colours, used on the figure only (a dot, a number),
 *  never as a fill behind text. `null` is a quiet plum dot: a line with no tone. */
export type Tone = "good" | "watch" | "act";

export function toneOf(value: string | null | undefined): Tone | null {
  return value === "good" || value === "watch" || value === "act" ? value : null;
}

export function Dot({ tone }: { tone: Tone | null }): JSX.Element {
  return <span class="tone-dot" data-tone={tone ?? "none"} aria-hidden="true" />;
}
