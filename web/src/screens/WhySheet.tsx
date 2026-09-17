import type { JSX } from "preact";
import type { FeedItemOut } from "../api/types";
import type { Strings } from "../strings";
import { Sheet } from "../ui/kit";

/** The Why sheet's lines for one card (RE-08): the backend's own `why.lines`, already in the
 *  reader's voice and language, and already saying so when a part is withheld — one line at a
 *  time, plain words, nothing composed here. Older pages the phone kept before this shipped
 *  carry no `lines`, so this falls back to the one sentence they do carry (`why.plain`). */
export function whySheetLines(item: FeedItemOut | null): string[] {
  if (!item) return [];
  const lines = item.why.lines;
  if (Array.isArray(lines) && lines.every((line) => typeof line === "string") && lines.length > 0) {
    return lines;
  }
  return typeof item.why.plain === "string" && item.why.plain ? [item.why.plain] : [];
}

/** "Why am I seeing this?" (docs/recommendation-engine.md §3.3): the card's evidence, as
 *  plain lines, over the feed — its own Close, closed by the scrim too (`Sheet`). */
export function WhySheet({ item, onClose, s }: { item: FeedItemOut | null; onClose: () => void; s: Strings }): JSX.Element {
  const lines = whySheetLines(item);
  return (
    <Sheet title={s.feed.whyTitle} open={item !== null} onClose={onClose} closeLabel={s.shell.close} testId="why-sheet">
      {lines.map((line, at) => (
        <p key={at} data-testid="why-sheet-line">
          {line}
        </p>
      ))}
    </Sheet>
  );
}
