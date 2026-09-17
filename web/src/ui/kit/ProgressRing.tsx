import type { JSX } from "preact";

/** The progress ring (Health Overview): a circle filled as far as a real count goes, a big number
 *  in its middle and a plain label under it.
 *
 *  Never a score (docs/design-direction.md, "The one rule"): the ring holds a number he can
 *  check against what he did — doses taken this week, "12 of 14" — and the label says what it
 *  is. The number and the label are text, so the screen reader and 200% text read them; the ring
 *  itself is decorative. */
export function ProgressRing({ done, of, figure, label, testId }: { done: number; of: number; figure: string; label: string; testId?: string }): JSX.Element {
  const radius = 42;
  const around = 2 * Math.PI * radius;
  const share = of > 0 ? Math.min(1, Math.max(0, done / of)) : 0;
  return (
    <div class="ring" data-testid={testId}>
      <svg class="ring-art" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
        <circle class="ring-track" cx="50" cy="50" r={radius} />
        <circle class="ring-fill" cx="50" cy="50" r={radius} stroke-dasharray={`${(share * around).toFixed(2)} ${around.toFixed(2)}`} transform="rotate(-90 50 50)" />
      </svg>
      <div class="ring-centre">
        <span class="ring-number" data-testid={testId ? `${testId}-figure` : undefined}>
          {figure}
        </span>
        <span class="ring-label">{label}</span>
      </div>
    </div>
  );
}
