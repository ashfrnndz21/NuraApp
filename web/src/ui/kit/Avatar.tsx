import type { JSX } from "preact";
import type { Tint } from "./Tint";

/** The first letter of a name, as the person would write it: one character, whatever the
 *  script (a Chinese name's first character, never half of one). */
export function initial(name: string): string {
  const first = Array.from(name.trim())[0];
  return first ? first.toLocaleUpperCase() : "";
}

interface AvatarProps {
  name: string;
  /** The person whose papers these are, in the lighter plum; the signed-in person is full plum. */
  soft?: boolean;
  /** Their own uploaded photo, when they have one. Never a stock face: with none, their initial. */
  photo?: string | null;
  /** The initial on a tint instead of Plum (a row of family). */
  tint?: Tint;
  size?: "large";
}

/** A person: their own photo, else the initial of their name in a round. Decorative beside their
 *  name or a word that says who; never the only thing that says it. */
export function Avatar({ name, soft, photo, tint, size }: AvatarProps): JSX.Element {
  const classes = ["avatar", soft && "soft", tint && "tinted", size, photo && "photo"].filter(Boolean).join(" ");
  if (photo) return <img class={classes} src={photo} alt="" aria-hidden="true" />;
  return (
    <span class={classes} data-tint={tint} aria-hidden="true">
      {initial(name)}
    </span>
  );
}
