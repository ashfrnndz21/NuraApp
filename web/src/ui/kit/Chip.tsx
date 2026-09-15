import type { ComponentChildren, JSX } from "preact";
import { Dot, type Tone } from "./Dot";

/** A chip (docs/design-system.md §4): glass, 12px radius, Ink text — never white on a colour.
 *  Drivers, tags, sources, what to bring. A tone, when there is one, is a dot beside the word. */
export function Chip({ children, tone, testId }: { children: ComponentChildren; tone?: Tone | null; testId?: string }): JSX.Element {
  return (
    <span class="glass-chip" data-testid={testId} data-tone={tone ?? undefined}>
      {tone && <Dot tone={tone} />}
      {children}
    </span>
  );
}

/** Chips wrap onto as many rows as they need; nothing scrolls sideways. */
export function ChipRow({ children, testId, label }: { children: ComponentChildren; testId?: string; label?: string }): JSX.Element {
  return (
    <div class="chip-row" data-testid={testId} role={label ? "group" : undefined} aria-label={label}>
      {children}
    </div>
  );
}
