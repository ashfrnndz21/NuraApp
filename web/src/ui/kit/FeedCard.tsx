import type { ComponentChildren, JSX } from "preact";
import type { Tone } from "./Dot";
import { Icon, type IconName } from "./icons";
import { WhyLine } from "./Provenance";

interface FeedCardProps {
  title?: string | null;
  /** One number, and its colour on the figure only. */
  figure?: string | number | null;
  tone?: Tone | null;
  /** One direction, in a word, beside the number ("better than March" comes from the backend). */
  direction?: string | null;
  lines?: readonly string[];
  /** The backend's boundary lines, under the card's own. */
  boundary?: readonly string[];
  /** Where it came from: the backend's source line. */
  source?: string | null;
  /** Why it is here: the backend's "why am I seeing this". */
  why?: string | null;
  /** A clip's poster, or a player strip. */
  media?: ComponentChildren;
  /** The one action. */
  action?: ComponentChildren;
  /** The spoken twin's button, at the foot beside the why line. */
  hear?: ComponentChildren;
  icon?: IconName;
  paper?: boolean;
  settled?: boolean;
  testId?: string;
  children?: ComponentChildren;
}

/** The card grammar (docs/design-system.md §4): one number, one direction, one colour, one
 *  action; the source in caption size; why it is here under a hairline; its spoken twin. Every
 *  word on it is the backend's or the catalogue's, and it lays out in normal flow, top to
 *  bottom — nothing is drawn over a line. */
export function FeedCard({ title, figure, tone, direction, lines = [], boundary = [], source, why, media, action, hear, icon, paper = true, settled, testId, children }: FeedCardProps): JSX.Element {
  const classes = ["tile", paper ? "paper" : "glass", "card", settled && "settled"].filter(Boolean).join(" ");
  const hasFigure = figure !== undefined && figure !== null && figure !== "";
  return (
    <section class={classes} data-testid={testId}>
      {(title || icon) && (
        <div class="card-head">
          {icon && (
            <span class="card-icon">
              <Icon name={icon} />
            </span>
          )}
          {title && <h2 class="title">{title}</h2>}
        </div>
      )}
      {hasFigure && (
        <p class="card-figure" data-tone={tone ?? undefined}>
          <span class="number">{figure}</span>
          {direction && <span class="card-direction">{direction}</span>}
        </p>
      )}
      {lines.length > 0 && (
        <div class="lines">
          {lines.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
      )}
      {children}
      {media}
      {boundary.length > 0 && (
        <div class="lines boundary" data-testid="boundary">
          {boundary.map((line, at) => (
            <p key={at}>{line}</p>
          ))}
        </div>
      )}
      {source && <p class="provenance">{source}</p>}
      {action}
      {(why || hear) && (
        <div class="card-foot">
          <WhyLine text={why} />
          {hear}
        </div>
      )}
    </section>
  );
}
