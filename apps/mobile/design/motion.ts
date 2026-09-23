/**
 * Motion tokens — the single source of truth (section 35).
 *
 * Copied verbatim from the `:root` block of
 * `docs/design/experience-blueprint-v2.html` (blueprint-v2 / redesign
 * branch). Same names, same values as the reference — only the units
 * change from CSS (ms strings, cubic-bezier()) to plain numbers/tuples
 * usable from Reanimated.
 *
 * Nothing in `components/` may hard-code a duration: read it from here
 * (enforced by `scripts/lint-motion.js`). `components/motion/motionTokens.ts`
 * re-exports this file for backward compatibility with existing imports —
 * do not add new values there, add them here.
 */

// ---- durations, in ms (css: Xms) -------------------------------------
export const motionFast = 140;
export const motionStandard = 320;
export const motionSlow = 560;

// ---- cubic-bezier control points (css: cubic-bezier(x1,y1,x2,y2)) ----
export type Bezier = readonly [number, number, number, number];
export const springGentle: Bezier = [0.22, 0.61, 0.36, 1];
export const springStandard: Bezier = [0.2, 0.8, 0.2, 1];
export const springBouncy: Bezier = [0.34, 1.42, 0.5, 1];

// ---- composite durations paired with a curve in the reference --------
export const fadeEnter = motionStandard; // + springGentle
export const fadeExit = motionFast; // + springGentle
export const cardEnter = 520; // + springGentle
export const sheetEnter = 550; // + springStandard

export const scalePress = 0.985;
export const pressIn = 100; // linear
export const pressOut = 260; // + springBouncy

export const orbIdle = 7000;
export const orbListening = 3400;
export const orbThinking = 2200;
export const orbResponding = 4200;

export const wordEnter = motionSlow;
export const statusIn = 350;
export const statusOut = 220;
export const sweep = 1500;

export const breathe = 4500;
export const drift = 16000;
export const driftSlow = 20000;
export const bob = 6000;

export const staggerDense = 80;
export const staggerRows = 110;
export const staggerTight = 150;
export const staggerMid = 200;
export const staggerStep = 230;
export const staggerWide = 260;
export const staggerCards = 300;

export const chartDraw = 900;
export const countUp = 1100;
export const alarmReveal = 60;
export const mediaRun = 9000;
export const atmosFade = 800;

export const streamHead = 85;
export const streamSub = 50;
export const streamBody = 36;
export const streamSheet = 58;
export const streamSpoken = 210;
export const wordHold = 220;

export const thinkHold = 1050;
export const thinkPage = 430;
export const busyHold = 950;
export const beat = 700;
export const autoPick = 1200;
export const userPick = 6000;

/**
 * Sheet drag thresholds (`BottomSheet.tsx`). v2's CSS has no drag handler
 * to measure these from (`design-build-2-map.md`'s own finding: the
 * blueprint's sheet opens/closes via CSS transform only) — these are the
 * spike's own physics, named here instead of left as magic numbers inline.
 */
export const sheetDismissDistance = 110; // px
export const sheetDismissVelocity = 800; // px/s

/** Every duration/curve above, addressable by its blueprint `--name`. */
export const motionTokens = {
  'motion-fast': motionFast,
  'motion-standard': motionStandard,
  'motion-slow': motionSlow,
  'spring-gentle': springGentle,
  'spring-standard': springStandard,
  'spring-bouncy': springBouncy,
  'fade-enter': fadeEnter,
  'fade-exit': fadeExit,
  'card-enter': cardEnter,
  'sheet-enter': sheetEnter,
  'scale-press': scalePress,
  'press-in': pressIn,
  'press-out': pressOut,
  'orb-idle': orbIdle,
  'orb-listening': orbListening,
  'orb-thinking': orbThinking,
  'orb-responding': orbResponding,
  'word-enter': wordEnter,
  'status-in': statusIn,
  'status-out': statusOut,
  sweep,
  breathe,
  drift,
  'drift-slow': driftSlow,
  bob,
  'stagger-dense': staggerDense,
  'stagger-rows': staggerRows,
  'stagger-tight': staggerTight,
  'stagger-mid': staggerMid,
  'stagger-step': staggerStep,
  'stagger-wide': staggerWide,
  'stagger-cards': staggerCards,
  'chart-draw': chartDraw,
  'count-up': countUp,
  'alarm-reveal': alarmReveal,
  'media-run': mediaRun,
  'atmos-fade': atmosFade,
  'stream-head': streamHead,
  'stream-sub': streamSub,
  'stream-body': streamBody,
  'stream-sheet': streamSheet,
  'stream-spoken': streamSpoken,
  'word-hold': wordHold,
  'think-hold': thinkHold,
  'think-page': thinkPage,
  'busy-hold': busyHold,
  beat,
  'auto-pick': autoPick,
  'user-pick': userPick,
} as const;
