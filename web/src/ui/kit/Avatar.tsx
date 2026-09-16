import type { JSX } from "preact";

/** The first letter of a name, as the person would write it: one character, whatever the
 *  script (a Chinese name's first character, never half of one). */
export function initial(name: string): string {
  const first = Array.from(name.trim())[0];
  return first ? first.toLocaleUpperCase() : "";
}

/** A person, as the initial of their name in a circle. Decorative beside their name or a word
 *  that says who; never the only thing that says it. `soft`: the person whose papers these
 *  are, in the lighter plum; the signed-in person is full plum. */
export function Avatar({ name, soft }: { name: string; soft?: boolean }): JSX.Element {
  return (
    <span class={soft ? "avatar soft" : "avatar"} aria-hidden="true">
      {initial(name)}
    </span>
  );
}
