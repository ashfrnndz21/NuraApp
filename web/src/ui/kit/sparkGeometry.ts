/** The sparkline's geometry, worked out apart from drawing so it can be tested: the backend's
 *  values in their order, scaled into the box, and the range band when the backend gave one.
 *  Nothing is smoothed, fitted or extrapolated: one vertex per value. */

export interface Point {
  x: number;
  y: number;
}

export interface SparkGeometry {
  points: Point[];
  /** "M x,y L x,y …": the 1.5px Ink line. Empty for a single value. */
  path: string;
  /** The last value's point: always marked. */
  last: Point;
  /** The range band, in box units, when the backend gave a low and a high. */
  band: { y: number; height: number } | null;
}

export interface SparkBox {
  width: number;
  height: number;
  /** Room kept at the top and bottom so the marked point is never clipped. */
  pad?: number;
  band?: { low: number; high: number } | null;
}

const round = (n: number) => Math.round(n * 10) / 10;

export function sparkGeometry(values: readonly number[], box: SparkBox): SparkGeometry | null {
  const finite = values.filter((value) => Number.isFinite(value));
  if (finite.length === 0) return null;
  const pad = box.pad ?? 6;
  const band = box.band && Number.isFinite(box.band.low) && Number.isFinite(box.band.high) ? box.band : null;
  const every = band ? [...finite, band.low, band.high] : finite;
  let low = Math.min(...every);
  let high = Math.max(...every);
  if (high === low) {
    low -= 1;
    high += 1;
  }
  const y = (value: number) => round(pad + ((high - value) / (high - low)) * (box.height - 2 * pad));
  const step = finite.length > 1 ? (box.width - 2 * pad) / (finite.length - 1) : 0;
  const points = finite.map((value, at) => ({ x: round(finite.length > 1 ? pad + at * step : box.width - pad), y: y(value) }));
  const path = points.length > 1 ? points.map((p, at) => `${at === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ") : "";
  const bandBox = band ? { y: y(band.high), height: round(y(band.low) - y(band.high)) } : null;
  return { points, path, last: points[points.length - 1]!, band: bandBox };
}
