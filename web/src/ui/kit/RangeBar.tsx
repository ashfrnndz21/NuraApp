import type { JSX } from "preact";

export interface RangeBarProps {
  /** Where the in-range band starts and how wide it is, each 0-100 (% of the bar's width). */
  bandStart: number;
  bandWidth: number;
  /** Where the reading's own marker sits, 0-100. */
  markerAt: number;
  /** Amber when the reading is outside the band, sage when it is inside — never inferred from
   *  the numbers here, so a caller who computed the flag elsewhere cannot disagree with the bar. */
  tone: "ok" | "attention";
  /** The reading and its range, read once by a screen reader — the bar itself is decorative. */
  label: string;
  testId?: string;
}

/** A reading against the range printed on its paper (docs/design/experience-blueprint.html `.bar`): the
 *  in-range segment as a sage band, the reading itself as a marker — amber-ringed when it falls
 *  outside the band, sage-ringed when it is inside. */
export function RangeBar({ bandStart, bandWidth, markerAt, tone, label, testId }: RangeBarProps): JSX.Element {
  return (
    <div class="range-bar" role="img" aria-label={label} data-testid={testId}>
      <span class="range-bar-segment" style={{ left: `${bandStart}%`, width: `${bandWidth}%` }} />
      <span class={`range-bar-marker${tone === "ok" ? " ok" : ""}`} style={{ left: `${markerAt}%` }} />
    </div>
  );
}
