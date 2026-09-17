import type { ComponentChildren, JSX } from "preact";

/** The illustration system (docs/design-direction.md, "Illustration system"): one drawn style —
 *  soft flat shapes, rounded, warm, friendly without being childish — in the palette's own
 *  tokens, so every picture themes with `tokens.css` and stays crisp at any size.
 *
 *  Every illustration is decorative. It is hidden from the screen reader, it is never focusable,
 *  and it never carries something the words beside it do not say. */

/** A token's colour for a shape: `fill={c("plum")}` reads `var(--plum)`. SVG presentation
 *  attributes do not read custom properties in every browser, so the colour goes in `style`. */
export function paint(token: string): JSX.CSSProperties {
  return { fill: `var(--${token})` };
}

export function line(token: string, width = 2.5): JSX.CSSProperties {
  return { fill: "none", stroke: `var(--${token})`, strokeWidth: width, strokeLinecap: "round", strokeLinejoin: "round" };
}

export interface IlloProps {
  /** More classes: where the screen places and sizes it. */
  class?: string;
  /** Fill the box the screen gives it, cropping the edges, rather than fit inside it. */
  cover?: boolean;
  testId?: string;
}

export function Illo({ viewBox, children, class: extra, testId, name, cover }: IlloProps & { viewBox: string; children: ComponentChildren; name: string }): JSX.Element {
  return (
    <svg
      class={["illo", extra].filter(Boolean).join(" ")}
      viewBox={viewBox}
      preserveAspectRatio={cover ? "xMidYMid slice" : undefined}
      aria-hidden="true"
      focusable="false"
      role="presentation"
      data-illustration={name}
      data-testid={testId}
    >
      {children}
    </svg>
  );
}
