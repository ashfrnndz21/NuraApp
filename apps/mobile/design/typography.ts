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

/**
 * A pragmatic pixel scale (FIX BEFORE MERGE, independent review of PR
 * #332): every screen size that doesn't already have a named role above
 * — prefer a named export (`kicker`, `bodyText`, `cardTitle.primary`,
 * …) where one fits; reach for `fontSize[n]` only for a one-off (a back
 * button's glyph, a pill label) that isn't really "a headline" or "a
 * body" in its own right. Every value here is one already used
 * somewhere in `experience-blueprint-v2.html`'s own CSS, not invented.
 */
export const fontSize = {
  11: 11,
  11.5: 11.5,
  12: 12,
  12.5: 12.5,
  13: 13,
  13.5: 13.5,
  14: 14,
  14.5: 14.5,
  15: 15,
  15.5: 15.5,
  16: 16,
  17: 17,
  18: 18,
  19: 19,
  20: 20,
  22: 22,
  25: 25,
  29: 29,
  33: 33,
} as const;
