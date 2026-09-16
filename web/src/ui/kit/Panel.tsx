import type { JSX } from "preact";
import { Dot, type Tone } from "./Dot";

export interface PanelRow {
  key?: string;
  text: string;
  /** A quiet note at the end of the row: a source, how often. */
  meta?: string | null;
  tone?: Tone | null;
  /** Rows with a dot keep the dot's column even when this row has no tone. */
  dotted?: boolean;
}

/** A titled list in one tile: "What changed", "Watching for Pa", "Sent to Pa this week". Each
 *  row is the backend's line, a dot in its tone on the figure only, and its note at the end;
 *  a hairline between rows. Glass unless it carries a decision. */
export function PanelList({ title, rows, note, paper, testId }: { title: string; rows: readonly PanelRow[]; note?: string | null; paper?: boolean; testId?: string }): JSX.Element {
  const dotted = rows.some((row) => row.tone !== undefined || row.dotted);
  return (
    <section class={paper ? "tile paper panel" : "tile glass panel"} data-testid={testId}>
      <h2 class="panel-title">{title}</h2>
      <ul class="panel-list">
        {rows.map((row, at) => (
          <li key={row.key ?? at} data-tone={row.tone ?? undefined}>
            {dotted && <Dot tone={row.tone ?? null} />}
            <span class="panel-text">{row.text}</span>
            {row.meta && <span class="panel-meta">{row.meta}</span>}
          </li>
        ))}
      </ul>
      {note && <p class="why-line">{note}</p>}
    </section>
  );
}
