import type { ComponentChildren, JSX } from "preact";

interface HeroProps {
  /** "Good morning, Pa." — his Today only, above everything, in his language. */
  greeting?: string;
  /** A quiet line under the greeting: the date. */
  sub?: string;
  /** The label over the figure: "How things are today" (her Home). */
  label?: string;
  /** The one big number or state word per screen. */
  figure?: string | number | null;
  /** What the figure counts or means, in the backend's words; null for none. */
  words?: string | null;
  children?: ComponentChildren;
  testId?: string;
}

/** The hero (docs/design-system.md §4): sits directly on the wash, no tile. One label, one
 *  large figure or state word, one line — every word the backend's or the catalogue's. His
 *  Today: the greeting and the day, then his count and its words ("2", "medicines with
 *  breakfast"). Her Home: "How things are today", the State's word ("Steady") and its line, with
 *  the sparkline and the drivers as chips under it. The screen decides when there is no figure
 *  or no line: never a count from the phone's kept page, never a reassuring line while a
 *  red-flag card is on the page (`homeHeroWords`). */
export function Hero({ greeting, sub, label, figure, words, children, testId }: HeroProps): JSX.Element {
  return (
    <header class="hero-block" data-testid={testId}>
      {greeting && <p class="hero-greeting">{greeting}</p>}
      {sub && <p class="hero-sub">{sub}</p>}
      {label && <p class="hero-label">{label}</p>}
      {figure !== undefined && figure !== null && figure !== "" && (
        <p class="hero-figure" data-testid="hero-figure">
          {figure}
        </p>
      )}
      {words && (
        <p class="hero-words" data-testid="hero-words">
          {words}
        </p>
      )}
      {children}
    </header>
  );
}
