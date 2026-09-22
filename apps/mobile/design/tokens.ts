/**
 * Structural tokens (radii, sheet metrics) — the single source of truth
 * (section 35). Source: `docs/design/experience-blueprint-v2.html`
 * `.phone`-scoped rules, cross-checked against `docs/design/DESIGN_SYSTEM.md`
 * §3 ("Radius") for the named divergences this file fixes.
 */

export const radii = {
  /** `.card[data-tier="primary"]` / `--radius-card`. */
  cardPrimary: 28,
  /** `.card` base / `--radius-tile`. */
  cardBase: 26,
  cardSecondary: 22,
  cardTertiary: 16,
  /**
   * Sheet top corners. Was 28px in `BottomSheet.tsx` — v2 (`.sheet`) and
   * the web kit's `--radius-sheet` both say 30px (DESIGN_SYSTEM.md §3
   * divergence #2, fixed here).
   */
  sheet: 30,
  row: 18,
  chip: 999,
  pill: 999,
  /**
   * Media poster. Was 18px in `MediaCard.tsx` — v2's `.poster` is 22px
   * (DESIGN_SYSTEM.md §3 divergence #3, the largest of the three, fixed
   * here).
   */
  mediaPoster: 22,
} as const;

export { sheetDismissDistance, sheetDismissVelocity } from './motion';

/** Re-export everything, so `import { tokens } from '../design/tokens'` has one door in. */
export * as motion from './motion';
export * as colors from './colors';
export * as typography from './typography';
