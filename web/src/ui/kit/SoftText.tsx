import type { JSX } from "preact";
import { ACCENT_WORD_RE, WORD_GAP_BODY_MS, WORD_GAP_HEADLINE_MS, plainWords, splitWords } from "../motion";

type Pace = "headline" | "body";
type Tag = "p" | "h1" | "h2" | "h3" | "span";

interface SoftTextProps {
  text: string;
  /** The text this same line held last render, if any — how a caller streaming an answer tells
   *  `SoftText` which words are already on screen. Left off (or unchanged from `text`), every
   *  word is new, which is exactly right for text that arrives complete: every word animates in
   *  together on mount. A caller need not remember anything beyond what it already has (the
   *  streamed text so far); `SoftText` itself holds no state of its own (deliberately hookless,
   *  like the rest of `web/src/ui/kit/Conversation.tsx`). */
  previousText?: string;
  /** `headline` (62ms between words, motion.ts `WORD_GAP_HEADLINE_MS`) or `body` (36ms,
   *  `WORD_GAP_BODY_MS`) — the blueprint's own two paces (`stream()`'s default `per` versus the
   *  36ms it uses for a body paragraph). */
  pace?: Pace;
  as?: Tag;
  className?: string;
  testId?: string;
}

/** Text arriving word by word, blurred to sharp (docs/design/experience-blueprint.html `.w`,
 *  `stream()`): every word new since `previousText` gets a fresh `animation-delay`
 *  (`web/src/ui/kit/kit.css` `.soft-word-enter`), staggered `WORD_GAP_*` apart; a word already
 *  present in `previousText` renders plain and never replays — Preact keeps its existing DOM node
 *  untouched (same key, same computed style), so the browser never restarts its animation.
 *
 *  `*word*` marks the one italic serif accent a line may carry (blueprint `.ser`); stripped of
 *  its `*`s wherever the word is drawn. The full text is always in the DOM: a visually-hidden
 *  (`.sr-only`, base.css) span carries the plain reading as real text content — not `aria-label`,
 *  which axe's `aria-prohibited-attr` rightly refuses on a plain paragraph/heading role — and
 *  every word span is `aria-hidden`, so a screen reader hears the line once, at once, never word
 *  by word.
 *
 *  Under `prefers-reduced-motion: reduce` this reads as plain text: the same global rule that
 *  turns off every animation in the app (`web/src/ui/base.css`) removes `.soft-word-enter`'s
 *  entrance too, so every word is simply there — no branch needed here for it. */
export function SoftText({ text, previousText = "", pace = "headline", as = "p", className, testId }: SoftTextProps): JSX.Element {
  const Tag = as;
  const words = splitWords(text);
  const already = previousText === text ? words.length : splitWords(previousText).length;
  const gap = pace === "body" ? WORD_GAP_BODY_MS : WORD_GAP_HEADLINE_MS;
  return (
    <Tag class={className} data-testid={testId}>
      <span class="sr-only">{plainWords(text)}</span>
      {words.map((word, at) => {
        const m = word.match(ACCENT_WORD_RE);
        const shown = m ? `${m[1]}${m[2]}` : word;
        const isNew = at >= already;
        const cls = ["soft-word", m && "accent", isNew && "soft-word-enter"].filter(Boolean).join(" ");
        const style = isNew ? { animationDelay: `${(at - already) * gap}ms` } : undefined;
        return (
          <span key={at} class={cls} aria-hidden="true" style={style}>
            {shown}
          </span>
        );
      })}
    </Tag>
  );
}
