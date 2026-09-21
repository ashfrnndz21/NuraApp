import { useRef, useState } from "preact/hooks";
import type { JSX } from "preact";
import { Icon } from "./icons";

export type ThreeState = "idle" | "busy" | "done";

interface ThreeStateButtonProps {
  /** The label in each of its three states (docs/design/experience-blueprint.html `openSheet()`:
   *  "Copy" → "Copying…" → "Copied", a check beside it). */
  label: string;
  busyLabel: string;
  doneLabel: string;
  /** What the tap really does. `ThreeStateButton` never times a wait of its own — `busy` holds
   *  for exactly as long as this promise takes, `done` is only ever the promise having really
   *  resolved. A rejection returns the button to `idle` rather than pretending to have finished. */
  onAct: () => Promise<void>;
  variant?: "light" | "dark" | "plain";
  /** Disabled in the `idle` state only — a caller's own gate (checkpoint 3's "Keep these
   *  questions", stopped while nothing is selected) — never overrides `busy`/`done`, which stay
   *  disabled regardless. */
  disabled?: boolean;
  testId?: string;
}

/** A button that goes through three real states — label, busy, done with a check
 *  (docs/design/experience-blueprint.html `openSheet()`'s own CTA) — never further than the
 *  action it names has actually reached. */
export function ThreeStateButton({ label, busyLabel, doneLabel, onAct, variant = "light", disabled = false, testId }: ThreeStateButtonProps): JSX.Element {
  const [state, setState] = useState<ThreeState>("idle");
  // A ref, not the state above, guards against a real double-tap: Preact's state update from the
  // first click is not yet committed when a second click fires in the same tick (both would
  // otherwise still read "idle" and both call `onAct`). `acting` is read and set synchronously,
  // the same guard the blueprint's own `openSheet()` uses (`b.dataset.s`).
  const acting = useRef(false);

  async function handleClick(): Promise<void> {
    if (acting.current) return;
    acting.current = true;
    setState("busy");
    try {
      await onAct();
      setState("done");
    } catch {
      acting.current = false;
      setState("idle");
    }
  }

  const cls = ["btn", variant !== "plain" && variant, state === "busy" && "busy", state === "done" && "done"].filter(Boolean).join(" ");
  return (
    <button type="button" class={cls} onClick={handleClick} disabled={state !== "idle" || disabled} aria-live="polite" data-testid={testId} data-state={state}>
      {state === "done" && <Icon name="check" />}
      {state === "idle" ? label : state === "busy" ? busyLabel : doneLabel}
    </button>
  );
}
