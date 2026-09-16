import type { ComponentChildren, JSX } from "preact";
import { PillButton } from "./PillButton";

interface SheetProps {
  title: string;
  open: boolean;
  onClose: () => void;
  closeLabel: string;
  children: ComponentChildren;
  testId?: string;
}

/** A sheet (docs/design-system.md §2: 28px radius): paper, over the screen it was opened from,
 *  with its own Close — a button, never a swipe. It is a modal dialog: the page under it is
 *  dimmed and a tap on the dim closes it too. What is in it scrolls inside it. */
export function Sheet({ title, open, onClose, closeLabel, children, testId }: SheetProps): JSX.Element | null {
  if (!open) return null;
  return (
    <div class="sheet-layer" data-testid={testId}>
      <div class="sheet-scrim" aria-hidden="true" onClick={onClose} />
      <section class="sheet-panel" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <header class="sheet-head">
          <h2 id="sheet-title" class="title" tabIndex={-1}>
            {title}
          </h2>
          <PillButton compact icon="close" onClick={onClose} testId="sheet-close">
            {closeLabel}
          </PillButton>
        </header>
        <div class="sheet-body">{children}</div>
      </section>
    </div>
  );
}
