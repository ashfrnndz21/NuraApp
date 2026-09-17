import type { ComponentChildren, JSX } from "preact";

interface HeroProps {
  /** "Good morning, Pa." — above everything, in his language, in the serif display face. */
  greeting?: string;
  /** The question under the greeting: "How are you feeling today?" (docs/design-direction.md). */
  ask?: string;
  /** A quiet line under the greeting: the date. */
  sub?: string;
  /** The label over the figure: "How things are today" (her Home). */
  label?: string;
  /** The one big number or state word per screen. */
  figure?: string | number | null;
  /** What the figure counts or means, in the backend's words; null for none. */
  words?: string | null;
  /** The illustration beside the greeting. Decorative: it says nothing the words do not. */
  art?: ComponentChildren;
  /** A wave beside the greeting. Decorative, hidden from the screen reader: the words stand alone. */
  wave?: boolean;
  children?: ComponentChildren;
  testId?: string;
}

/** The hero (docs/design-system.md §4, warmed by docs/design-direction.md): sits directly on the
 *  ground, no tile. The greeting in the serif display face with its question under it and a warm
 *  illustration beside it; then one label, one large figure or state word, one line — every word
 *  the backend's or the catalogue's. His Today: his count and its words ("2", "medicines with
 *  breakfast"). Her Home: "How things are today", the State's word ("Steady") and its line, with
 *  the sparkline and the drivers as chips under it. The screen decides when there is no figure
 *  or no line: never a count from the phone's kept page, never a reassuring line while a
 *  red-flag card is on the page (`homeHeroWords`). */
export function Hero({ greeting, ask, sub, label, figure, words, art, wave, children, testId }: HeroProps): JSX.Element {
  // The hero carries the screen's heading, because on Today and on Home it is the first thing
  // on the page and there is no title bar above it: the greeting, or her label over the State's
  // word. A screen with no heading is a screen a screen reader cannot start at, and Tab would
  // go on from wherever the last screen's button was (`ui/focus.ts`).
  return (
    <header class="hero-block" data-testid={testId}>
      <div class="hero-top">
        <div class="hero-text">
          {greeting ? (
            <div class="hero-hello">
              <h1 class="hero-greeting">{greeting}</h1>
              {wave && (
                <span class="hero-wave" aria-hidden="true">
                  👋
                </span>
              )}
            </div>
          ) : (
            label && <h1 class="hero-label hero-heading">{label}</h1>
          )}
          {ask && <p class="hero-ask">{ask}</p>}
          {sub && <p class="hero-sub">{sub}</p>}
        </div>
        {art && <div class="hero-art">{art}</div>}
      </div>
      {greeting && label && <p class="hero-label">{label}</p>}
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
