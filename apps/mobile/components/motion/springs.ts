import { Easing, type WithSpringConfig, type WithTimingConfig } from 'react-native-reanimated';

import { motionFast, motionStandard, motionSlow, springBouncy, springGentle, springStandard } from './motionTokens';

/**
 * Reanimated has no native cubic-bezier "spring" — `withSpring` takes
 * physical params (damping/stiffness/mass), not a bezier curve. These are
 * tuned to *read* like the reference's three curves at the reference's
 * own durations, and are the only spring configs a component may use.
 */
export const springs: Record<'gentle' | 'standard' | 'bouncy', WithSpringConfig> = {
  gentle: { damping: 22, stiffness: 170, mass: 0.9, overshootClamping: false },
  standard: { damping: 20, stiffness: 210, mass: 1, overshootClamping: false },
  bouncy: { damping: 13, stiffness: 260, mass: 1, overshootClamping: false },
};

/** Bezier-timing equivalents, for places that must animate on a clock (e.g. opacity/blur where a spring would never settle predictably). */
export const easings = {
  gentle: Easing.bezier(...springGentle),
  standard: Easing.bezier(...springStandard),
  bouncy: Easing.bezier(...springBouncy),
};

export const timing = {
  fast: (overrides?: Partial<WithTimingConfig>): WithTimingConfig => ({
    duration: motionFast,
    easing: easings.gentle,
    ...overrides,
  }),
  standard: (overrides?: Partial<WithTimingConfig>): WithTimingConfig => ({
    duration: motionStandard,
    easing: easings.gentle,
    ...overrides,
  }),
  slow: (overrides?: Partial<WithTimingConfig>): WithTimingConfig => ({
    duration: motionSlow,
    easing: easings.gentle,
    ...overrides,
  }),
};
