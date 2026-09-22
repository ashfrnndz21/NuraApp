/**
 * Typography tokens — the single source of truth (section 35).
 *
 * Source: `docs/design/experience-blueprint-v2.html`, `.phone`-scoped
 * rules only (the product's own type, not the documentation chrome's
 * `.top h1` / `.spec h2` / `.tag` etc.).
 */

export const fontFamily = {
  sans: 'Figtree',
  serif: 'Instrument Serif',
} as const;

/** Base body text (`body{font-size:15px;line-height:1.5}` inside `.phone`). */
export const bodyBase = { fontSize: 15, lineHeight: 22.5, fontWeight: '400' } as const;

/** `.kick` — the small eyebrow line above a headline. */
export const kicker = { fontSize: 14.5, opacity: 0.85, fontWeight: '400' } as const;

/** `.big` — the large editorial headline (Home, Welcome). */
export const headlineLarge = {
  fontSize: 33,
  lineHeight: 35.6,
  fontWeight: '300',
  letterSpacing: -0.66,
} as const;

/** `.center .big` variant, smaller stage. */
export const headlineCenter = { fontSize: 29, fontWeight: '300' } as const;

/** `.head` — "what it means" / insight headline. */
export const headlineInsight = {
  fontSize: 25,
  lineHeight: 29.25,
  fontWeight: '300',
  letterSpacing: -0.375,
} as const;

/** `.ser` — the italic serif accent word inside a headline. */
export const serifAccent = {
  fontFamily: fontFamily.serif,
  fontStyle: 'italic',
  fontSizeEm: 1.12,
} as const;

/** `.card h3` / `.card p` per tier (DESIGN_SYSTEM.md §2). */
export const cardTitle = {
  primary: { fontSize: 18, fontWeight: '400' },
  secondary: { fontSize: 16, fontWeight: '400' },
  tertiary: { fontSize: 15, fontWeight: '500', opacity: 0.82 },
} as const;

export const cardBody = {
  primary: { fontSize: 14.5, lineHeight: 21.03 },
  secondary: { fontSize: 14, lineHeight: 20.3 },
  tertiary: { fontSize: 15.5, fontWeight: '300', lineHeight: 20.93 },
} as const;

/** `.val` — a deterministic value line (report table, Ask answers). */
export const valueLine = {
  fontSize: 20,
  fontWeight: '600',
  letterSpacing: -0.2,
  fontVariant: ['tabular-nums'] as const,
};

/** `.status` — the orb's streaming status line. */
export const statusLine = { fontSize: 18.5, fontWeight: '300' } as const;

/** `.body` — sheet / answer body copy. */
export const bodyText = { fontSize: 15.5, lineHeight: 22.48 } as const;

/** `.note` — the small provenance / caveat line under an answer. */
export const noteText = { fontSize: 12.5, opacity: 0.78, lineHeight: 17.5 } as const;
