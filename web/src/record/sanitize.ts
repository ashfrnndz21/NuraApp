/** Extractor-written text is hostile until he confirms it (redesign package 11, the owner's
 *  safety rule): a label's own field -- its `name`, what a box or a screenshot printed --
 *  may be SHOWN to him on the confirmation card, because looking at it is the point of
 *  confirming, but it must never be sent to a model, a tool, an ask/analyst result, used to
 *  build a query, logged, or rendered as HTML. Preact already renders every string prop as a
 *  text node (nothing here ever uses `dangerouslySetInnerHTML`), so markup in the text is
 *  inert by construction; what this guards against is the text spoofing the *screen itself*:
 *  a bidi-override character that visually reorders a line, a control character, or a
 *  newline made to look like a second row of copy Nura never wrote -- all folded to a plain
 *  space -- and a very long string that would overflow or crowd out a card's own layout,
 *  capped with an ellipsis. */

/** Built from explicit `\uXXXX` escapes in an ordinary string, never as literal unicode
 *  characters in this file's own source (a control or bidi character sitting in a `.ts` file
 *  as a real byte makes git treat the whole file as binary, invisible to review from then
 *  on): C0 controls, DEL and NEL, the Unicode line terminators a `\n`-only strip misses
 *  (LINE/PARAGRAPH SEPARATOR), the zero-width and bidi-control characters (LRM/RLM through
 *  the bidi embedding/override/isolate controls, word joiner, BOM/ZWNBSP) — the same set
 *  `app.llm.ask_agent`'s own `_CONTROL_CHARS`/`_INVISIBLE_RANGES` holds a tool-bound field
 *  to, so a hostile field reads the same whether it is headed for a model or a screen — plus
 *  four more invisible characters that set carries but a hostile *display* field can reach
 *  and that one cannot: soft hyphen, Arabic letter mark, Mongolian vowel separator, and the
 *  Hangul filler (a blank that is not whitespace, so a plain `\s` collapse never catches it). */
const CONTROL_OR_BIDI = new RegExp(
  "[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\u007F\\u0085\\u00AD\\u061C\\u180E" +
    "\\u2028\\u2029\\u200B-\\u200F\\u202A-\\u202E\\u2060-\\u2069\\u3164\\uFEFF]",
  "gu",
);

export const DISPLAY_TEXT_MAX = 200;

/** The one function any screen must run extracted, unconfirmed text through before it is
 *  shown: control and bidi-override characters and newlines folded to a plain space, runs of
 *  whitespace collapsed, and the result capped to `max` characters with a trailing ellipsis.
 *  Never a truncation that leaves the string longer than `max` including the ellipsis. */
export function sanitizeDisplayText(raw: string | null | undefined, max: number = DISPLAY_TEXT_MAX): string {
  const text = typeof raw === "string" ? raw : "";
  const flattened = text.replace(CONTROL_OR_BIDI, " ").replace(/\s+/g, " ").trim();
  if (flattened.length <= max) return flattened;
  return `${flattened.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}
