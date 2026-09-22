import React from 'react';
import { Platform } from 'react-native';

import type { AmbientBackgroundProps } from './AmbientBackgroundCanvas';

/**
 * Public entry point. The real Skia implementation lives in
 * `AmbientBackgroundCanvas.tsx` — kept in a separate module because the
 * web target renders Skia through CanvasKit, a WASM binary loaded
 * asynchronously (`app/_layout.tsx`'s `useSkiaWebReady`). Any file that
 * statically imports `@shopify/react-native-skia` gets evaluated the
 * moment Metro parses the bundle, before that WASM load can finish, so
 * on web this component is loaded lazily through `WithSkiaWeb` instead;
 * on native (Expo Go) Skia is a synchronous JSI host object and this
 * just renders the real implementation directly.
 */
let NativeImpl: React.ComponentType<AmbientBackgroundProps> | null = null;
if (Platform.OS !== 'web') {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  NativeImpl = require('./AmbientBackgroundCanvas').AmbientBackground;
}

export function AmbientBackground(props: AmbientBackgroundProps) {
  if (Platform.OS === 'web') {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { WithSkiaWeb } = require('@shopify/react-native-skia/lib/module/web');
    return (
      <WithSkiaWeb
        getComponent={() => import('./AmbientBackgroundCanvas').then((m: any) => ({ default: m.AmbientBackground }))}
        componentProps={props}
        fallback={null}
      />
    );
  }
  return NativeImpl ? <NativeImpl {...props} /> : null;
}

export type { AmbientBackgroundProps };
