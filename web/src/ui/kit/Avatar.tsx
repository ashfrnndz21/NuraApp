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

/** Whether `url` is safe to hand to an `<img src>` here: the app's own origin (a path from its
 *  own upload, `/photos/...`), or a `blob:`/`data:` URL the phone made from a file he chose. An
 *  address of another site, however it is spelled — `//`, `http:`, `javascript:` — is refused:
 *  never a place to point his phone at a third party, and never a way to run script through
 *  `src`. Not exported: the drawing decides who gets a photo, nothing else. */
function samePlace(url: string): boolean {
  if (url.startsWith("blob:") || url.startsWith("data:")) return true;
  if (typeof window === "undefined") return false;
  try {
    return new URL(url, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
}

/** A person: their own photo, else the initial of their name in a round. Decorative beside their
 *  name or a word that says who; never the only thing that says it.
 *
 *  `photo` is only ever drawn when it is his own upload or the app's own place (`samePlace`
 *  above, reviewer #237 item 7): anything else — a photo url from an address book import, say,
 *  pointed at another site — falls back to his initial instead, the same as no photo at all. */
export function Avatar({ name, soft, photo, tint, size }: AvatarProps): JSX.Element {
  const safe = photo && samePlace(photo) ? photo : null;
  const classes = ["avatar", soft && "soft", tint && "tinted", size, safe && "photo"].filter(Boolean).join(" ");
  if (safe) return <img class={classes} src={safe} alt="" aria-hidden="true" />;
  return (
    <span class={classes} data-tint={tint} aria-hidden="true">
      {initial(name)}
    </span>
  );
}
