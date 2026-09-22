import React from 'react';
import { Canvas, Circle, Fill, Path, Skia, vec } from '@shopify/react-native-skia';
import type { SharedValue } from 'react-native-reanimated';

/**
 * The Skia line chart inside `ExpandableCard` (spec §16: it "draws
 * itself"). Split into its own module — see `AmbientBackground.tsx` for
 * why — so the web target can defer importing `@shopify/react-native-skia`
 * until CanvasKit has finished loading.
 */
export interface BPChartCanvasProps {
  points: ReadonlyArray<readonly [number, number]>;
  width: number;
  height: number;
  /** 0 → 1 trim of the stroke/fill — animated by the caller as the card expands. */
  progress: SharedValue<number>;
}

export function BPChartCanvas({ points, width, height, progress }: BPChartCanvasProps) {
  const sourceWidth = points[points.length - 1][0];
  const scaleX = (x: number) => (x / sourceWidth) * Math.max(width - 8, 40);

  const path = Skia.Path.Make();
  points.forEach(([x, y], i) => {
    const sx = scaleX(x);
    if (i === 0) path.moveTo(sx, y);
    else path.lineTo(sx, y);
  });
  const fillPath = path.copy();
  fillPath.lineTo(scaleX(points[points.length - 1][0]), height);
  fillPath.lineTo(scaleX(points[0][0]), height);
  fillPath.close();
  const lastPoint = points[points.length - 1];

  return (
    <Canvas style={{ width: '100%', height: height + 16 }} testID="bp-chart-canvas">
      <Fill color="transparent" />
      <Path path={fillPath} style="fill" color="rgba(169,211,174,0.18)" start={0} end={progress} />
      <Path path={path} style="stroke" strokeWidth={2.5} color="#a9d3ae" start={0} end={progress} />
      <Circle c={vec(scaleX(lastPoint[0]), lastPoint[1])} r={4.5} color="#a9d3ae" />
    </Canvas>
  );
}
