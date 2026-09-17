import type { JSX } from "preact";

/** A soft shimmering placeholder in a card's own shape, wherever a screen's content is
 *  loading — instead of a spinner on a blank page (docs/design-direction.md "Conversation,
 *  waiting and thinking"). A static wash under `prefers-reduced-motion` (design.css).
 *
 *  LOCAL STAND-IN: the foundation builder is building a shared skeleton card in
 *  `web/src/ui/kit`; once it lands on main, swap this for it rather than keeping two. */
export function SkeletonCard({ lines = 2, testId }: { lines?: number; testId?: string }): JSX.Element {
  return (
    <div class="skeleton-card" data-testid={testId ?? "skeleton-card"} aria-hidden="true">
      {Array.from({ length: lines }, (_, at) => (
        <div key={at} class={`skeleton-line${at === lines - 1 ? " short" : ""}`} />
      ))}
    </div>
  );
}
