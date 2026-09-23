import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

/**
 * `prefers-reduced-motion` (spec §25): movement off, state changes kept.
 * Every looping/translating animation in `components/` must gate on this;
 * orb/card/sheet state transitions stay (opacity/colour only), only the
 * *movement* is removed.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled?.().then((value) => {
      if (mounted) setReduced(!!value);
    });
    const sub = AccessibilityInfo.addEventListener?.('reduceMotionChanged', (value: boolean) => {
      setReduced(!!value);
    });
    return () => {
      mounted = false;
      sub?.remove?.();
    };
  }, []);

  return reduced;
}
