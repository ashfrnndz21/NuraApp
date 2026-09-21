import type { ComponentChildren, JSX } from "preact";

interface ConnectionRowProps {
  name: string;
  line?: string;
  /** A leading avatar/icon slot — the caller's own `Avatar` or `Icon`, decorative here. */
  lead?: ComponentChildren;
  /** A trailing slot — a chip, a chevron, a Flag. */
  trailing?: ComponentChildren;
  onClick?: () => void;
  testId?: string;
}

/** A person or a place, one row (docs/design/experience-blueprint.html `.row`/the family and
 *  services scenes): a lead, the name and a line under it, and a trailing slot. A real
 *  `<button>` when it goes anywhere, plain glass otherwise. */
export function ConnectionRow({ name, line, lead, trailing, onClick, testId }: ConnectionRowProps): JSX.Element {
  const body = (
    <>
      {lead}
      <span class="connection-row-name">
        <b>{name}</b>
        {line && <small>{line}</small>}
      </span>
      {trailing}
    </>
  );
  if (onClick) {
    return (
      <button type="button" class="connection-row" onClick={onClick} data-testid={testId}>
        {body}
      </button>
    );
  }
  return (
    <div class="connection-row" data-testid={testId}>
      {body}
    </div>
  );
}
