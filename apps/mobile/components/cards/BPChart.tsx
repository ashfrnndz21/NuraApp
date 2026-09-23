import React from 'react';
import { Platform } from 'react-native';

import type { BPChartCanvasProps } from './BPChartCanvas';

/**
 * Public entry point — see `components/ambient/AmbientBackground.tsx`
 * for why the Skia implementation is split into `BPChartCanvas.tsx` and
 * loaded lazily on web (`WithSkiaWeb`) but directly on native.
 */
let NativeImpl: React.ComponentType<BPChartCanvasProps> | null = null;
if (Platform.OS !== 'web') {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  NativeImpl = require('./BPChartCanvas').BPChartCanvas;
}

export function BPChart(props: BPChartCanvasProps) {
  if (Platform.OS === 'web') {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { WithSkiaWeb } = require('@shopify/react-native-skia/lib/module/web');
    return (
      <WithSkiaWeb
        getComponent={() => import('./BPChartCanvas').then((m: any) => ({ default: m.BPChartCanvas }))}
        componentProps={props}
        fallback={null}
      />
    );
  }
  return NativeImpl ? <NativeImpl {...props} /> : null;
}
