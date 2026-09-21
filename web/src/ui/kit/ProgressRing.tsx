import type { JSX } from "preact";

/** The progress ring (Health Overview): a circle filled as far as a real count goes, a big number
 *  in its middle, a plain label under it, and under that the plain line saying where the count
 *  came from ("From his readings, 12 Sep"), the backend's own words.
 *
 *  Never a score (docs/design-direction.md, "The one rule"): the ring holds a number he can
 *  check against what he did — doses taken this week, "12 of 14" — and the label says what it
 *  is. The number and the label are text, so the screen reader and 200% text read them; the ring
 *  itself is decorative.
 *
 *  Required, never optional: a count is only ever drawn with the line that grounds it, so a
 *  caller cannot show a figure with nothing behind it — an empty `source` draws nothing at all
 *  rather than a bare, ungrounded ring. */
export function ProgressRing({ done, of, figure, label, source, testId }: { done: number; of: number; figure: string; label: string; source: string; testId?: string }): JSX.Element | null {
  if (!source.trim()) return null;
  const radius = 42;
  const around = 2 * Math.PI * radius;
  const share = of > 0 ? Math.min(1, Math.max(0, done / of)) : 0;
  return (
    <div class="ring" data-testid={testId}>
      {/* The circle and its centred figure are one stacked box (`ring-circle`), sized once by
       *  `width: min(100%, 8.5rem)`; the source line is a normal block under it, in flow, never a
       *  grid sibling the circle could grow over. On a wide (desktop) screen `.ring`'s own parent
       *  can be far wider than a phone, and a bare CSS grid with two in-flow children collapses
       *  differently depending on how much extra width the implicit column gets — this fixed the
       *  overlap seen there (see base.css `.ring`, warm.css). */}
      <div class="ring-circle">
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
      <span class="ring-source" data-testid={testId ? `${testId}-source` : "ring-source"}>
        {source}
      </span>
    </div>
  );
}
