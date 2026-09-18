import type { ComponentChildren, JSX } from "preact";
import { pendingSignal } from "../../api/client";
import { SkeletonCard } from "./Conversation";

export interface PendingCardProps {
  /** The same key the screen passed as `Call.key` to the fetch this card is waiting on. */
  requestKey: string;
  /** The skeleton's own shape, in the card's silhouette. */
  shape?: "card" | "tile" | "row";
  lines?: number;
  /** The real content, drawn the instant nothing is pending under `requestKey`. */
  children: ComponentChildren;
  testId?: string;
}

/** The one wiring between a screen's fetch and the kit's Skeleton (docs/design/motion.md): while
 *  `client.ts` says a call tagged `requestKey` is out, this stands in the card's own shape;
 *  the moment it is not, the real content takes its place with a 160–220ms fade/slide in
 *  (`.card-enter`, `--settle`). A screen gets both — the wait shown honestly, the arrival
 *  animated — for free, by passing `key` to its `api()` call and wrapping the card in this one
 *  component; no per-screen loading flag, no per-screen animation.
 *
 *  It draws only what `pendingSignal` says is really true right now — a plain signal read, not a
 *  timer of its own. A call under 150ms is never seen as a skeleton at all: `.pending-skeleton`'s
 *  own CSS fade-in is delayed 150ms, so a quick answer replaces this node before the browser ever
 *  paints it. Reduce Motion (`ui/tokens.css`, `ui/warm.css`) turns both transitions instant and
 *  stops the skeleton's shimmer; it does not change what is shown, only how it arrives. */
export function PendingCard({ requestKey, shape = "card", lines = 3, children, testId }: PendingCardProps): JSX.Element {
  if (pendingSignal(requestKey).value > 0) {
    return (
      <div class="pending-skeleton" data-testid={testId ? `${testId}-skeleton` : undefined}>
        <SkeletonCard shape={shape} lines={lines} testId={testId ? `${testId}-skeleton-shape` : undefined} />
      </div>
    );
  }
  return (
    <div class="card-enter" data-testid={testId}>
      {children}
    </div>
  );
}
