import type { JSX } from "preact";

/** The progress ring (Health Overview): a circle holding only the number he can check against
 *  what he did — "5 of 5", "12 of 14" — then, under it, its own two lines: the plain label
 *  ("doses taken this week") and the plain line saying where the count came from ("From his
 *  readings, 12 Sep"), the backend's own words.
 *
 *  Never a score (docs/design-direction.md, "The one rule"). The number and the label are text,
 *  so the screen reader and 200% text read them; the ring itself is decorative.
 *
 *  Required, never optional: a count is only ever drawn with the line that grounds it, so a
 *  caller cannot show a figure with nothing behind it — an empty `source` draws nothing at all
 *  rather than a bare, ungrounded ring.
 *
 *  Only the number sits inside the circle (`ring-centre`) — the label and the source are both
 *  their own line under it, in normal flow, never fighting a circle's own curve for room. This
 *  is deliberate, not the original design's own choice: the label is the backend's own words
 *  and can run long ("Tablets taken this week"), long enough that at any real ring size it does
 *  not fit a circle's inner rectangle without crossing its stroke — the defect the owner
 *  screenshotted (#294). A short figure like "5 of 5" still has to fit the circle on its own,
 *  which is what `--ring-number`'s size (warm.css) and the padding here are tuned for, proved by
 *  `tests/e2e/health.spec.ts`'s own geometry assertions at both frame breakpoints and both text
 *  settings, for "5 of 5", "12 of 14" and "0 of 0". */
export function ProgressRing({ done, of, figure, label, source, testId }: { done: number; of: number; figure: string; label: string; source: string; testId?: string }): JSX.Element | null {
  if (!source.trim()) return null;
  const radius = 42;
  const around = 2 * Math.PI * radius;
  const share = of > 0 ? Math.min(1, Math.max(0, done / of)) : 0;
  return (
    <div class="ring" data-testid={testId}>
      {/* The circle is its own sized box (`ring-circle`), holding only the number — never a grid
       *  sibling, and never the label, that a circle's own curve could crop. On a wide (desktop)
       *  screen `.ring`'s own parent can be far wider than a phone; the circle stays a fixed size
       *  either way (see base.css `.ring`, warm.css). */}
      <div class="ring-circle">
        <svg class="ring-art" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
          <circle class="ring-track" cx="50" cy="50" r={radius} />
          <circle class="ring-fill" cx="50" cy="50" r={radius} stroke-dasharray={`${(share * around).toFixed(2)} ${around.toFixed(2)}`} transform="rotate(-90 50 50)" />
        </svg>
        <div class="ring-centre">
          <span class="ring-number" data-testid={testId ? `${testId}-figure` : undefined}>
            {figure}
          </span>
        </div>
      </div>
      <span class="ring-label">{label}</span>
      <span class="ring-source" data-testid={testId ? `${testId}-source` : "ring-source"}>
        {source}
      </span>
    </div>
  );
}
