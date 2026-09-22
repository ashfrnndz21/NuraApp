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

/**
 * `AIOrb` is the public name for the five-state orb (section 34). The
 * previous name `IntelligenceOrb` is kept below as a deprecated alias so
 * existing imports keep working while callers migrate — remove the alias
 * once no import of `IntelligenceOrb` remains anywhere in the app.
 */
export function AIOrb(props: IntelligenceOrbProps) {
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

/** @deprecated use `AIOrb` — kept until no import of this name remains. */
export const IntelligenceOrb = AIOrb;

export type { IntelligenceOrbProps, OrbSize } from './IntelligenceOrbCanvas';
