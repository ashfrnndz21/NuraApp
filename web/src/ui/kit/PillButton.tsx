import type { ComponentChildren, JSX } from "preact";
import { Icon, type IconName } from "./icons";

export type PillVariant = "primary" | "secondary" | "coral" | "quiet";

interface PillButtonProps {
  onClick: () => void;
  children: ComponentChildren;
  /** primary: the one Plum-filled pill a screen may have. secondary: a Paper outline. coral:
   *  "I'm not feeling well" and nothing else. quiet: a word in Plum, no outline. */
  variant?: PillVariant;
  icon?: IconName;
  /** As wide as its words, not the tile: Hear beside a source line. */
  compact?: boolean;
  disabled?: boolean;
  label?: string;
  testId?: string;
  pressed?: boolean;
}

const VARIANT_CLASS: Record<PillVariant, string | null> = {
  primary: "plum",
  secondary: null,
  coral: "coral",
  quiet: "quiet",
};

/** The pill button (docs/design-system.md §4). Full width in the patient's density, never
 *  under the target height. The icon, when there is one, sits beside its word. */
export function PillButton({ onClick, children, variant = "secondary", icon, compact, disabled, label, testId, pressed }: PillButtonProps): JSX.Element {
  const classes = ["pill", VARIANT_CLASS[variant], compact && "compact"].filter(Boolean).join(" ");
  return (
    <button type="button" class={classes} onClick={onClick} disabled={disabled} aria-label={label} aria-pressed={pressed} data-testid={testId} data-variant={variant}>
      {icon && <Icon name={icon} />}
      <span class="pill-word">{children}</span>
    </button>
  );
}
