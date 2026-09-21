import type { JSX } from "preact";

export type OrbSize = "lg" | "sm";

/** The living orb: the assistant (docs/design/experience-blueprint.html `.orb`/`.orb.lg`) — a
 *  conic gradient, blurred, with a soft highlight, always slowly turning. 128px at a greeting
 *  (`size="lg"`, breathing 4.5s), 36px beside a conversation (`size="sm"`, the default). While
 *  Nura is really working, `thinking` speeds the turn from 7s to 2.2s — never on a timer of its
 *  own, only ever set from the same real state a `StatusLine` beside it reads.
 *
 *  Purely decorative: `aria-hidden`, so a screen reader skips it and reads the words beside it
 *  instead. */
export function Orb({ size = "sm", thinking = false, testId }: { size?: OrbSize; thinking?: boolean; testId?: string }): JSX.Element {
  const cls = ["orb", size === "lg" && "lg", thinking && "thinking"].filter(Boolean).join(" ");
  return (
    <div class={cls} aria-hidden="true" data-testid={testId}>
      <i />
      <b />
    </div>
  );
}
