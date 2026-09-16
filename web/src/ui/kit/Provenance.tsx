import type { ComponentChildren, JSX } from "preact";

/** Where a thing came from, in caption size: "From the pharmacy label, 1 September." The
 *  backend's own source line, shown as it is. */
export function ProvenanceLine({ children, testId }: { children: ComponentChildren; testId?: string }): JSX.Element | null {
  if (children === null || children === undefined || children === "") return null;
  return (
    <p class="source-line" data-testid={testId}>
      {children}
    </p>
  );
}

/** Why a card is here: "You are seeing this because…" — the backend's `why`, under a hairline,
 *  in caption size. Nothing when the backend gave no reason. */
export function WhyLine({ text, testId }: { text: string | null | undefined; testId?: string }): JSX.Element | null {
  if (!text) return null;
  return (
    <p class="why-line" data-testid={testId ?? "why"}>
      {text}
    </p>
  );
}
