import type { JSX } from "preact";

export type FlagState = "ok" | "attention" | "question";

/** A reading's own flag (docs/design/experience-blueprint.html `.flag`/`.flag.hi`/`.flag.q`):
 *  sage "ok", amber "attention", or an outlined "question" for a reading Nura cannot place
 *  without more of the paper. Always the backend's own word — never invented here. */
export function Flag({ state, children, testId }: { state: FlagState; children: string; testId?: string }): JSX.Element {
  const cls = ["flag-chip", state !== "ok" && state].filter(Boolean).join(" ");
  return (
    <span class={cls} data-testid={testId}>
      {children}
    </span>
  );
}
