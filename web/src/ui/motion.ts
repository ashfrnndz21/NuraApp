/** The dusk-glass conversational kit's one source of timing numbers (docs/design/README.md,
 *  docs/design/experience-blueprint.html `<script>` — `stream`, `think`, `reveal`, `openSheet`
 *  are the reference engine; these are its own numbers, copied here as the single place every
 *  kit component reads them from, extending the existing motion kit (`web/src/ui/kit`,
 *  docs/design/motion.md) rather than replacing it — `--settle`/`--press`/`--wash-fade`
 *  (tokens.css) are untouched and still govern a card's entrance, a tap and the posture wash.
 *
 *  Every duration here is a CSS-driven one: nothing in `web/src/ui/kit` calls `setTimeout` to
 *  fake a wait (docs/design/motion.md §6, `tests/unit/ui/motion.test.tsx`'s grep test) — a
 *  component either sets a CSS `animation-delay` per word from `MOTION.wordGap*`, or listens for
 *  the browser's own `animationend`/`transitionend` event, never a clock of its own. The numbers
 *  below and the keyframes in `web/src/ui/base.css` (`.word-in`, `.status-line`, `.rv2`,
 *  `.action-sheet`) must be kept in sync by hand — CSS cannot import a JS constant — so a change
 *  here is not real until its matching literal in `base.css` changes too. */

/** Words arrive one by one, blurred to sharp (blueprint `.w`/`stream()`): the gap between one
 *  word and the next, in a headline versus a body line. */
export const WORD_GAP_HEADLINE_MS = 62;
export const WORD_GAP_BODY_MS = 36;
/** Each word's own fade-in, blur(5px)→0 plus opacity (blueprint `@keyframes win`, `.5s`). */
export const WORD_FADE_MS = 500;

/** The one status line, replaced in place with a light sweep (blueprint `.status`/`think()`):
 *  how long a line holds before the next one starts, and how long the blur-out between lines
 *  takes. The sweep itself loops for as long as a line is shown. */
export const STATUS_HOLD_MS = 1050;
export const STATUS_OUT_MS = 200;
export const STATUS_SWEEP_MS = 1500;

/** Structure assembles after the words: headline, then tabs, then rows one by one, then actions
 *  last (blueprint `.rv`/`reveal()`) — 0.55s opacity/blur(6px)/translateY(10px), each child
 *  staggered 110–260ms after the last. `REVEAL_STAGGER_MS` is the default gap `RevealGroup` uses
 *  between children; a caller may pass its own within the 110–260ms band. */
export const REVEAL_MS = 550;
export const REVEAL_STAGGER_MS = 140;
export const REVEAL_STAGGER_MIN_MS = 110;
export const REVEAL_STAGGER_MAX_MS = 260;

/** A sheet slides up over the shell (blueprint `.sheet`): 0.55s, the same eased curve every
 *  sheet in the app uses. */
export const SHEET_MS = 550;
export const SHEET_EASE = "cubic-bezier(.2,.8,.2,1)";

/** Whether motion should be skipped: `prefers-reduced-motion: reduce`, checked once per call
 *  rather than cached, so a setting changed mid-session (or in a test) is honoured at once. The
 *  app has no motion setting of its own beyond the OS/browser preference (searched: no
 *  `reduceMotion`/`prefersReducedMotion` store exists) — when one lands, this is the one place
 *  to add it. Safe with no `matchMedia` (a non-browser test environment): treats that as "no
 *  preference stated", i.e. motion runs. */
export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** `*...*` — the one italic serif accent a line may carry (blueprint `.ser`): stripped for the
 *  plain-text reading (`.sr-only`, reduced motion), matched for the styled span(s). Parsed
 *  across the WHOLE line first (#303 review, S6), never per space-split word: a per-word
 *  match missed a Chinese line (no spaces at all — the token never starts with `*` to begin
 *  with) and a multi-word accent like `*Mei Ling.*` (neither `*Mei` nor `Ling.*` closes on
 *  its own), both of which rendered their asterisks as literal text. A stray, unmatched
 *  asterisk (no closing partner on the same line) is left as ordinary text. */
const ACCENT_SPAN_RE = /\*([^*]+)\*/;

interface AccentSpan {
  text: string;
  accent: boolean;
}

function parseAccentSpans(text: string): AccentSpan[] {
  const spans: AccentSpan[] = [];
  let rest = text;
  for (;;) {
    const m = rest.match(ACCENT_SPAN_RE);
    if (!m || m.index === undefined) {
      if (rest.length > 0) spans.push({ text: rest, accent: false });
      return spans;
    }
    if (m.index > 0) spans.push({ text: rest.slice(0, m.index), accent: false });
    spans.push({ text: m[1]!, accent: true });
    rest = rest.slice(m.index + m[0].length);
  }
}

const CJK_RE = /[㐀-䶿一-鿿豈-﫿]/;

/** Whether `text` is CJK script — no spaces between words at all, so `SoftText`'s own per-word
 *  stagger needs a different "word" (`textUnits`) and its rendered spans need no inter-word
 *  gap (`web/src/ui/kit/kit.css` `.soft-word-tight`, unlike the Latin/Malay `margin-right` a
 *  space itself would otherwise be). */
export function isCJK(text: string): boolean {
  return CJK_RE.test(text);
}

function segmentForDisplay(text: string, tight: boolean): string[] {
  if (!tight) return text.split(" ").filter((w) => w.length > 0);
  // `Intl.Segmenter`'s own `"word"` granularity where the runtime has it (groups a multi-
  // character Chinese word as one stagger step, punctuation as its own); a plain per-
  // character fallback otherwise (`Array.from` — spreading a string — already reads by code
  // point, so a rare surrogate-pair character is never split in two either way).
  const SegmenterCtor = (Intl as unknown as { Segmenter?: new (locale?: string, options?: { granularity?: string }) => { segment(input: string): Iterable<{ segment: string }> } }).Segmenter;
  if (SegmenterCtor) {
    const segmenter = new SegmenterCtor(undefined, { granularity: "word" });
    return [...segmenter.segment(text)].map((piece) => piece.segment).filter((piece) => piece.length > 0);
  }
  return [...text];
}

/** One display unit for `SoftText`'s own per-word stagger: its shown text, whether the line's
 *  own `*...*` accent covers it, and whether it joins the next unit tight (CJK, no
 *  `margin-right` gap) or with the ordinary word gap (Latin/Malay). */
export interface TextUnit {
  text: string;
  accent: boolean;
  tight: boolean;
}

/** Split text into the units `SoftText` animates one at a time (`textUnits`) — accent spans
 *  parsed first, across the whole line, then each span segmented for display: Latin/Malay
 *  text on spaces (the blueprint's own `stream()` "word"), Chinese text (no spaces) by
 *  `Intl.Segmenter`/character (`segmentForDisplay`). */
export function textUnits(text: string): TextUnit[] {
  const tight = isCJK(text);
  const units: TextUnit[] = [];
  for (const span of parseAccentSpans(text)) {
    for (const piece of segmentForDisplay(span.text, tight)) {
      units.push({ text: piece, accent: span.accent, tight });
    }
  }
  return units;
}

/** Split text into words the way the blueprint's own `stream()` does (Latin/Malay only — see
 *  `textUnits` for the general, CJK-aware split `SoftText` itself now uses). Kept for any
 *  caller that only ever sees Latin/Malay text and wants the plain per-space word. */
export function splitWords(text: string): string[] {
  return text.split(" ").filter((w) => w.length > 0);
}

/** The plain-text reading of a line that may carry `*...*` accents: for the `.sr-only` span,
 *  and for the reduced-motion / non-JS fallback render. Reconstructs the original line
 *  exactly, asterisks stripped — never word-joined-with-a-space, which would wrongly insert
 *  spaces into a Chinese line that has none. */
export function plainWords(text: string): string {
  return parseAccentSpans(text)
    .map((span) => span.text)
    .join("");
}
