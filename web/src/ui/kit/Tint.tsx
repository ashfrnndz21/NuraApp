import type { ComponentChildren, JSX } from "preact";
import { Icon, type IconName } from "./icons";

/** The warm components (docs/design-direction.md): soft pastel-tinted cards and tiles, each its
 *  own colour, a line icon in Plum on a tinted square or circle. Every colour is a token
 *  (`tokens.css`, "Card tints"); a component names the tint, never a colour. */

export type Tint = "blush" | "lavender" | "sage" | "coral" | "cream" | "peach" | "butter" | "sky" | "paper";

/** A line icon in Plum on a tinted rounded square or circle. Decorative: the words beside it
 *  say what it is. */
export function IconBadge({ icon, tint = "lavender", shape = "square", size }: { icon: IconName; tint?: Tint; shape?: "square" | "circle"; size?: "small" | "large" }): JSX.Element {
  return (
    <span class={["icon-badge", size].filter(Boolean).join(" ")} data-tint={tint} data-shape={shape} aria-hidden="true">
      <Icon name={icon} />
    </span>
  );
}

interface TintCardProps {
  tint?: Tint;
  children: ComponentChildren;
  testId?: string;
  role?: "alert" | "status" | "group";
  label?: string;
  /** More classes: the screen's own layout for this card. */
  extra?: string;
}

/** The tinted card: a soft pastel ground, a large radius, a barely-there shadow. Ink words on
 *  every tint hold 7:1 (tests/unit/contrast.test.ts), so a decision may sit on one. */
export function TintCard({ tint = "paper", children, testId, role, label, extra }: TintCardProps): JSX.Element {
  return (
    <section class={["tint-card", extra].filter(Boolean).join(" ")} data-tint={tint} data-testid={testId} role={role} aria-label={label}>
      {children}
    </section>
  );
}

interface FeatureTileProps {
  icon: IconName;
  tint: Tint;
  label: string;
  caption: string;
  onClick: () => void;
  testId?: string;
}

/** The square feature tile (Home's "What would you like to do?", as the approved board draws it):
 *  its own tint, a line icon in Plum, a bold word and a small caption, centred. The whole tile is
 *  the button, and its name is the word and the caption together. */
export function FeatureTile({ icon, tint, label, caption, onClick, testId }: FeatureTileProps): JSX.Element {
  return (
    <button type="button" class="feature-tile" data-tint={tint} onClick={onClick} data-testid={testId}>
      <Icon name={icon} />
      <span class="feature-label">{label}</span>
      <span class="feature-caption">{caption}</span>
    </button>
  );
}

/** How a reading sits, as a small pill ("Good"). Only where the reading's own range backs it
 *  (docs/design-direction.md, "The one rule"): the screen decides that, never this pill. The
 *  word is always there; the colour only repeats it. */
export function StatusPill({ tone, children, testId }: { tone: "good" | "watch" | "act"; children: ComponentChildren; testId?: string }): JSX.Element {
  return (
    <span class="status-pill" data-tone={tone} data-testid={testId}>
      {children}
    </span>
  );
}
