import type { ComponentChildren, JSX } from "preact";

/** The voice-note and clip player's strip (docs/design-system.md §4): glass, a large play
 *  target, the transcript under it at body size. It styles the player it is given — the clip
 *  button today, W4's shared player once it is on main — and never plays anything itself. */
export function PlayerStrip({ children, playing, testId }: { children: ComponentChildren; playing?: boolean; testId?: string }): JSX.Element {
  return (
    <div class="player-strip" data-playing={playing ? "true" : undefined} data-testid={testId}>
      {children}
    </div>
  );
}
