import type { ComponentChildren, JSX } from "preact";

interface GlassProps {
  children: ComponentChildren;
  /** `card` (26px radius, the blueprint's `.card`) or `row` (18px, the blueprint's `.row`). */
  shape?: "card" | "row";
  as?: "div" | "section" | "article";
  testId?: string;
  className?: string;
}

/** The one shared translucent surface (docs/design/experience-blueprint.html `.glass`): fill
 *  `rgba(255,255,255,.10)`, a 1px `rgba(255,255,255,.22)` border, 18px backdrop blur — every
 *  card, row and chip in the kit is this, or close to it (tokens.css `--glass-*`). A plain box
 *  with no behaviour of its own: layout and padding are the caller's. */
export function Glass({ children, shape = "card", as = "div", testId, className }: GlassProps): JSX.Element {
  const Tag = as;
  const cls = ["glass-surface", shape === "card" ? "glass-card" : "glass-row", className].filter(Boolean).join(" ");
  return (
    <Tag class={cls} data-testid={testId}>
      {children}
    </Tag>
  );
}
