import React from 'react';
import { Platform } from 'react-native';

import type { IntelligenceOrbProps } from './IntelligenceOrbCanvas';

/**
 * Public entry point — see `AmbientBackground.tsx` for why the Skia
 * implementation is split into `IntelligenceOrbCanvas.tsx` and loaded
 * lazily on web (`WithSkiaWeb`) but directly on native.
 */
let NativeImpl: React.ComponentType<IntelligenceOrbProps> | null = null;
if (Platform.OS !== 'web') {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  NativeImpl = require('./IntelligenceOrbCanvas').IntelligenceOrb;
}

export function IntelligenceOrb(props: IntelligenceOrbProps) {
  if (Platform.OS === 'web') {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { WithSkiaWeb } = require('@shopify/react-native-skia/lib/module/web');
    return (
      <WithSkiaWeb
        getComponent={() => import('./IntelligenceOrbCanvas').then((m: any) => ({ default: m.IntelligenceOrb }))}
        componentProps={props}
        fallback={null}
      />
    );
  }
  return NativeImpl ? <NativeImpl {...props} /> : null;
}

export type { IntelligenceOrbProps, OrbSize } from './IntelligenceOrbCanvas';
