import type { ComponentChildren, JSX } from "preact";
import { REVEAL_STAGGER_MS } from "../motion";

/** One piece of structure assembling in (docs/design/experience-blueprint.html `.rv`/`.rv.in`):
 *  opacity/blur(6px)/translateY(10px) → none, over `REVEAL_MS` (motion.ts). Deliberately
 *  hookless: the entrance is CSS `@starting-style` (`web/src/ui/kit/kit.css` `.reveal-item`), the
 *  browser's own way to say "transition from this on first paint" — so mounting is the only
 *  trigger, with no `useEffect`/`requestAnimationFrame` dance to fake the same thing. */
export function Reveal({ children, className, testId }: { children: ComponentChildren; className?: string; testId?: string }): JSX.Element {
  return (
    <div class={["reveal-item", className].filter(Boolean).join(" ")} data-testid={testId}>
      {children}
    </div>
  );
}

/** A group of `Reveal`s, staggered 110-260ms apart (`REVEAL_STAGGER_MS`, motion.ts) via each
 *  child's own `transition-delay` — headline, then tabs, then rows one by one, then actions
 *  last, all from one mount, no timer involved. */
export function RevealGroup({ children, gap, className, testId }: { children: ComponentChildren[]; gap?: number; className?: string; testId?: string }): JSX.Element {
  const items = Array.isArray(children) ? children : [children];
  const step = gap ?? REVEAL_STAGGER_MS;
  return (
    <div class={["reveal-group", className].filter(Boolean).join(" ")} data-testid={testId}>
      {items.map((child, at) => (
        <div key={at} class="reveal-item" style={{ transitionDelay: `${at * step}ms` }}>
          {child}
        </div>
      ))}
    </div>
  );
}
