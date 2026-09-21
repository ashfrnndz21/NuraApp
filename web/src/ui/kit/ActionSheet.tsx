import { useEffect, useRef } from "preact/hooks";
import type { ComponentChildren, JSX } from "preact";
import { ThreeStateButton } from "./ThreeStateButton";

interface ActionSheetCta {
  label: string;
  busyLabel: string;
  doneLabel: string;
  onAct: () => Promise<void>;
}

interface ActionSheetProps {
  open: boolean;
  title: string;
  sub?: string;
  /** The body slot — whatever the caller streams or lays out under the title. */
  children?: ComponentChildren;
  notNowLabel: string;
  onClose: () => void;
  /** The one strong action, a `ThreeStateButton` (label → busy → done). Left off, the sheet is
   *  "Not now" alone. */
  cta?: ActionSheetCta;
  testId?: string;
}

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'));
}

/** A bottom sheet sliding up over the shell (docs/design/experience-blueprint.html `.sheet`,
 *  `openSheet()`): a grab handle, a title, a sub-line, a body slot, "Not now", and the one
 *  `ThreeStateButton`. Focus moves into it on open and is trapped there (Tab cycles inside it
 *  only) until it closes, when focus returns to whatever opened it; Escape closes it the same
 *  way "Not now" does. The slide-up itself needs no state of its own (`web/src/ui/kit/kit.css`
 *  `.action-sheet`'s `@starting-style`) — only the focus trap is a real side effect, so it is
 *  the one thing here that needs a hook. */
export function ActionSheet({ open, title, sub, children, notNowLabel, onClose, cta, testId }: ActionSheetProps): JSX.Element | null {
  const panelRef = useRef<HTMLElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreFocus.current = (document.activeElement as HTMLElement) ?? null;
    panelRef.current?.focus();

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const items = focusableIn(panelRef.current);
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      restoreFocus.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div class="action-sheet-layer" data-testid={testId}>
      <div class="action-sheet-scrim" aria-hidden="true" onClick={onClose} />
      <section ref={panelRef} class="action-sheet" role="dialog" aria-modal="true" aria-labelledby="action-sheet-title" tabIndex={-1}>
        <span class="action-sheet-grab" aria-hidden="true" />
        <div>
          <h3 id="action-sheet-title" class="action-sheet-title">
            {title}
          </h3>
          {sub && <p class="action-sheet-sub">{sub}</p>}
        </div>
        {children && <div class="action-sheet-body">{children}</div>}
        <div class="action-sheet-actions">
          <button type="button" class="btn" onClick={onClose} data-testid="action-sheet-not-now">
            {notNowLabel}
          </button>
          {cta && <ThreeStateButton label={cta.label} busyLabel={cta.busyLabel} doneLabel={cta.doneLabel} onAct={cta.onAct} testId="action-sheet-cta" />}
        </div>
      </section>
    </div>
  );
}
