import type { ComponentChildren, JSX } from "preact";

interface TileProps {
  children: ComponentChildren;
  testId?: string;
  role?: "alert" | "status" | "group";
  /** More classes: `settled` after Taken, `sheet` for the 28px radius. */
  extra?: string;
  label?: string;
}

function classes(surface: "paper" | "glass", extra?: string): string {
  return ["tile", surface, extra].filter(Boolean).join(" ");
}

/** Paper (docs/design-system.md §1): near-opaque white inside the rounded silhouette. Anything
 *  a decision depends on sits here — a dose, a number, a date, a button. */
export function PaperTile({ children, testId, role, extra, label }: TileProps): JSX.Element {
  return (
    <section class={classes("paper", extra)} data-testid={testId} role={role} aria-label={label}>
      {children}
    </section>
  );
}

/** Glass: translucent, blurred, luminous. Chrome and context that needs no decision — a family
 *  note, "questions ready", gaps, the chief's dense views. */
export function GlassTile({ children, testId, role, extra, label }: TileProps): JSX.Element {
  return (
    <section class={classes("glass", extra)} data-testid={testId} role={role} aria-label={label}>
      {children}
    </section>
  );
}

/** A section's quiet label on the wash: "Now", "For you today". Sentence case, never caps. */
export function SectionLabel({ children, testId }: { children: ComponentChildren; testId?: string }): JSX.Element {
  return (
    <h2 class="section-label" data-testid={testId}>
      {children}
    </h2>
  );
}
