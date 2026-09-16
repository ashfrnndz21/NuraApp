import type { JSX } from "preact";
import type { Tone } from "./Dot";
import { sparkGeometry } from "./sparkGeometry";

const WIDTH = 320;
const HEIGHT = 64;

interface SparklineProps {
  values: readonly number[];
  /** What the line says, for the screen reader: one whole line from the catalogue ("The last
   *  blood pressure had a top number of 138."), never the numbers strung together. */
  label: string;
  band?: { low: number; high: number } | null;
  /** The last point's colour: a state colour on the figure, or Ink. */
  tone?: Tone | null;
  /** The visible caption under the line: what its number is ("Blood pressure, the top
   *  number"), or the direction in words from the backend. */
  caption?: string | null;
  testId?: string;
}

/** The sparkline (docs/design-system.md §4): a 1.5px Ink line, the last point marked, the range
 *  band at 8% Plum when there is a range. No axes, no gridlines, no ticks — in either density. */
export function Sparkline({ values, label, band, tone, caption, testId }: SparklineProps): JSX.Element | null {
  const shape = sparkGeometry(values, { width: WIDTH, height: HEIGHT, band });
  if (!shape) return null;
  return (
    <figure class="sparkline" data-testid={testId ?? "sparkline"}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} preserveAspectRatio="xMidYMid meet">
        {shape.band && <rect class="spark-band" x="0" y={shape.band.y} width={WIDTH} height={shape.band.height} rx="6" />}
        {shape.path && <path class="spark-line" d={shape.path} />}
        <circle class="spark-last" cx={shape.last.x} cy={shape.last.y} r="4" data-tone={tone ?? "none"} />
      </svg>
      {caption && <figcaption class="spark-caption">{caption}</figcaption>}
    </figure>
  );
}
