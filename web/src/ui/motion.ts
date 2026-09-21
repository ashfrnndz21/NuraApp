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

/** `*word*` — the one italic serif accent a headline may carry (blueprint `.ser`): stripped for
 *  the plain-text reading (aria-label, reduced motion), matched for the styled span. */
export const ACCENT_WORD_RE = /^\*(.+)\*([.,?!:;]?)$/;

/** Split text into words the way the blueprint's own `stream()` does, so `SoftText` and a plain
 *  accessible label agree on what a "word" is (split on a single space). */
export function splitWords(text: string): string[] {
  return text.split(" ").filter((w) => w.length > 0);
}

/** The plain-text reading of a line that may carry `*word*` accents: for `aria-label`, and for
 *  the reduced-motion / non-JS fallback render. */
export function plainWords(text: string): string {
  return splitWords(text)
    .map((w) => {
      const m = w.match(ACCENT_WORD_RE);
      return m ? `${m[1]}${m[2]}` : w;
    })
    .join(" ");
}
