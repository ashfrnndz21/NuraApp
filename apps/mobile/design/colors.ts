/**
 * Colour tokens — the single source of truth (section 35).
 *
 * Source: `docs/design/experience-blueprint-v2.html`, `.phone` and its
 * atmosphere (the product's own dusk-glass world — see
 * `docs/design/DESIGN_SYSTEM.md` §1 for why this is a *different* palette
 * from the documentation-chrome `:root` block in the same file).
 *
 * `components/motion/motionTokens.ts`'s `phoneTokens`/`colorsLight`/
 * `colorsDark` re-export from here — do not add new colour values there.
 */

/** The phone's own visual world (`.phone` in the reference) — dusk gradient + atmosphere blobs. */
export const phoneTokens = {
  /** `--c`: ink / primary text, the one text colour the whole world reads on. */
  c: '#fbf6f0',
  /** `--g`: glass fill. Was hard-coded as 8% in `NuraCard.tsx` — v2 is 10% (DESIGN_SYSTEM.md §1 divergence, fixed here). */
  g: 'rgba(255,255,255,0.10)',
  /** `--gb`: glass border. Was hard-coded as 16% in `NuraCard.tsx` — v2 is 22% (DESIGN_SYSTEM.md §1 divergence, fixed here). */
  gb: 'rgba(255,255,255,0.22)',
  atmosGradient: ['#4b3c69', '#372b52', '#1f1731'] as const,
  atmosGradientAngleDeg: 180,
  atmosLayerA: { color: '#e7b48f', opacity: 0.42, animated: true as const },
  atmosLayerB: { color: '#8f78b3', opacity: 0.45, animated: true as const },
  /** Third, static atmosphere layer (`.atmos i.c`) — no drift animation. */
  atmosLayerC: { color: '#15101f', opacity: 0.55, animated: false as const },
} as const;

/** Semantic colours — deliberately a separate hue family from the accent purple (DESIGN_SYSTEM.md §1). */
export const semanticColors = {
  good: '#a9d3ae',
  watch: '#f3b562',
  act: '#f08a8a',
  inkOnLight: '#2b2140',
  /** v2 itself has two near-identical dark inks (`.flag` vs `.btn.red`); the spike kept the `.flag` one. */
  inkOnTone: '#231a12',
  /** `.btn.done`'s own dark ink on the sage "done"/confirmed fill (`#16301c`) — a darker relative of `inkOnTone`, not the same value. */
  inkOnGood: '#16301c',
} as const;

/** Card accent colour per variant (`NuraCard.tsx` `ACCENT`). */
export const cardAccentColors = {
  insight: '#c9a9e8',
  reminder: '#f3b562',
  media: '#9fd0ff',
  metric: '#a9d3ae',
  recommendation: '#e7b48f',
  document: '#fbe3cf',
  'ai-summary': '#c9a9e8',
  action: '#a9d3ae',
  alert: '#f3b562',
} as const;

/** Documentation-tool light palette (`:root`, undarkened) — chrome only, never the product. */
export const colorsLight = {
  paper: '#f6f2f7',
  panel: '#ffffff',
  ink: '#231a33',
  soft: '#5d5270',
  line: '#ddd3e6',
  plum: '#4f3a78',
  plumInk: '#ffffff',
  ready: '#1f7a4a',
  readyBg: '#dcf1e4',
  part: '#8a5a00',
  partBg: '#fbe9c6',
  todo: '#9b2c4a',
  todoBg: '#fadde5',
  blocked: '#5d5270',
  blockedBg: '#e7e0ee',
} as const;

/** Documentation-tool dark palette (`:root[data-theme="dark"]`) — chrome only, never the product. */
export const colorsDark = {
  paper: '#15111d',
  panel: '#1e1829',
  ink: '#efe8f6',
  soft: '#b3a8c4',
  line: '#3a3049',
  plum: '#b9a3e6',
  plumInk: '#1a1326',
  ready: '#8fdcb0',
  readyBg: '#16382a',
  part: '#f3c777',
  partBg: '#3d2f10',
  todo: '#f4a0b6',
  todoBg: '#431a27',
  blocked: '#b3a8c4',
  blockedBg: '#2c2438',
} as const;

export type ColorTokens = typeof colorsDark;
