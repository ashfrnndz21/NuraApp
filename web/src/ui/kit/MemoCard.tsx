import type { ComponentChildren, JSX } from "preact";

interface MemoCardProps {
  title?: string;
  /** The person's own words, one line each, shown in quotes: never reworded here. */
  quote: readonly string[];
  /** When it was filed, as the backend says it. */
  filed?: string | null;
  /** The appointment it is filed against, as the backend says it. */
  attached?: string | null;
  /** The spoken twin. */
  hear?: ComponentChildren;
  testId?: string;
}

/** The memo card (docs/design-system.md §4): paper, the person's own words in quotes, the day
 *  it was filed and the visit it is attached to. The same card in both densities. The quotes
 *  are the language's own (`<q>`), so Chinese gets its own marks. */
export function MemoCard({ title, quote, filed, attached, hear, testId }: MemoCardProps): JSX.Element {
  return (
    <section class="tile paper memo" data-testid={testId ?? "memo-card"}>
      {title && <h2 class="title">{title}</h2>}
      <blockquote class="memo-quote">
        {quote.map((line, at) => (
          <p key={at}>
            <q>{line}</q>
          </p>
        ))}
      </blockquote>
      {filed && <p class="source-line">{filed}</p>}
      {attached && <p class="source-line">{attached}</p>}
      {hear}
    </section>
  );
}
