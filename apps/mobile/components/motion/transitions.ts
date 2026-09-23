import type { WithSpringConfig, WithTimingConfig } from 'react-native-reanimated';

import * as tokens from './motionTokens';
import { easings, springs, timing } from './springs';

/**
 * The named transitions of spec §24: `motion.fast/standard/slow`,
 * `spring.gentle/standard/bouncy`, `fade.enter/exit`, `scale.press`,
 * `card.enter`, `sheet.enter`, `orb.idle/listening/thinking/responding`.
 * Components import from here (or from `springs`/`motionTokens` directly),
 * never a literal number.
 */
export const motion = {
  fast: tokens.motionFast,
  standard: tokens.motionStandard,
  slow: tokens.motionSlow,
};

export const spring = springs;

export const fade = {
  enter: timing.standard({ duration: tokens.fadeEnter, easing: easings.gentle }) as WithTimingConfig,
  exit: timing.fast({ duration: tokens.fadeExit, easing: easings.gentle }) as WithTimingConfig,
};

export const scale = {
  press: {
    to: tokens.scalePress,
    in: { duration: tokens.pressIn, easing: easings.gentle } as WithTimingConfig,
    out: springs.bouncy as WithSpringConfig,
  },
};

export const card = {
  enter: { duration: tokens.cardEnter, easing: easings.gentle } as WithTimingConfig,
};

export const sheet = {
  enter: springs.standard as WithSpringConfig,
  enterMs: tokens.sheetEnter,
};

export const orb = {
  idle: tokens.orbIdle,
  listening: tokens.orbListening,
  thinking: tokens.orbThinking,
  responding: tokens.orbResponding,
};

export const stagger = {
  dense: tokens.staggerDense,
  rows: tokens.staggerRows,
  tight: tokens.staggerTight,
  mid: tokens.staggerMid,
  step: tokens.staggerStep,
  wide: tokens.staggerWide,
  cards: tokens.staggerCards,
};
