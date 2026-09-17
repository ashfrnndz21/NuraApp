import type { ComponentChildren, JSX } from "preact";
import { Icon, type IconName } from "./icons";
import { IconBadge, type Tint } from "./Tint";

/** A section's heading with, when there is more of it elsewhere, a "View all" on its right:
 *  "Upcoming — View all". The heading is a real h2; the link's name says what it opens. */
export function SectionHeader({
  title,
  action,
  testId,
}: {
  title: string;
  action?: { word: string; label?: string; onClick: () => void; testId?: string };
  testId?: string;
}): JSX.Element {
  return (
    <div class="section-head" data-testid={testId}>
      <h2 class="section-title">{title}</h2>
      {action && (
        <button type="button" class="view-all" onClick={action.onClick} aria-label={action.label} data-testid={action.testId}>
          {action.word}
        </button>
      )}
    </div>
  );
}

interface ListRowProps {
  /** What leads the row: an avatar, or an icon badge. */
  lead: ComponentChildren;
  title: string;
  line?: string | null;
  /** On the right: a time, a count. */
  trailing?: string | null;
  onClick?: () => void;
  testId?: string;
}

/** A row in a list (Connect's messages, a list of people): what leads it, a title, one line, and
 *  on its right a time. A row that opens something is one button, the whole row its target. */
export function ListRow({ lead, title, line, trailing, onClick, testId }: ListRowProps): JSX.Element {
  const body = (
    <>
      <span class="list-lead">{lead}</span>
      <span class="list-text">
        <span class="list-title">{title}</span>
        {line && <span class="list-line">{line}</span>}
      </span>
      {trailing && <span class="list-trailing">{trailing}</span>}
    </>
  );
  return onClick ? (
    <button type="button" class="list-row" onClick={onClick} data-testid={testId}>
      {body}
    </button>
  ) : (
    <div class="list-row" data-testid={testId}>
      {body}
    </div>
  );
}

/** A metric row (Health Overview): an icon in its own tinted square, the label, and the value —
 *  big and bold where it is the point of the row — with the plain line under it saying where
 *  the value came from ("From his readings, 12 Sep"), the backend's own words.
 *
 *  Required, never optional: a reading is only ever drawn with the line that grounds it, so a
 *  caller cannot show a number with nothing behind it — an empty `source` draws nothing at all
 *  rather than a bare, ungrounded value. */
export function MetricRow({ icon, tint, label, value, unit, source, testId }: { icon: IconName; tint: Tint; label: string; value: string; unit?: string; source: string; testId?: string }): JSX.Element | null {
  if (!source.trim()) return null;
  return (
    <div class="metric-row" data-testid={testId}>
      <IconBadge icon={icon} tint={tint} size="small" />
      <span class="metric-label">{label}</span>
      <span class="metric-value">
        {value}
        {unit && <span class="metric-unit"> {unit}</span>}
      </span>
      <span class="metric-source" data-testid={testId ? `${testId}-source` : "metric-source"}>
        {source}
      </span>
    </div>
  );
}

/** The round arrow button in a card's corner (Reference A): it opens the card. Its name says
 *  what it opens, since the arrow alone says nothing. */
export function ArrowButton({ label, onClick, testId }: { label: string; onClick: () => void; testId?: string }): JSX.Element {
  return (
    <button type="button" class="arrow-button" aria-label={label} onClick={onClick} data-testid={testId}>
      <Icon name="arrow" />
    </button>
  );
}
