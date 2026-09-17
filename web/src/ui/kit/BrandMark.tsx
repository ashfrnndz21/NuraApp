import type { JSX } from "preact";

/** Every mark on screen at once needs its own gradient id (see below); a plain counter, not
 *  `useId()` — the design system's components use no hooks, so `tests/unit/ui/render.ts` can
 *  call them as plain functions, exactly as Preact would. */
let instances = 0;

/** The mark (docs/brand/BRAND.md): two strokes that meet at the top and never close at the
 *  bottom — plum on the left, the aura on the right — and the dot inside. Fixed; drawn from
 *  `docs/brand/nura-mark.svg` as-is, at the header's size. Decorative: the app's name is said
 *  by the page, not by the picture.
 *
 *  `speaking` is the mark's one motion (§7): while a voice note or a clip plays, the aura
 *  drifts through its two colours over four seconds and the dot breathes by 6% — both driven
 *  by CSS `@keyframes` in `design.css` under `.brand-mark[data-speaking="true"]`, so a screen
 *  that never sets it (the header's `Brand`) is always idle. `prefers-reduced-motion` drops
 *  the animation for a static opacity change, per §7's own fallback. The gradient's id is
 *  unique per instance: several marks speak on one screen — a feed of cards, each with its
 *  own Hear — and a shared id would let the browser's first definition win for all of them,
 *  freezing every other instance's colours to whichever drew first. */
export function BrandMark({ size = 32, speaking = false }: { size?: number; speaking?: boolean }): JSX.Element {
  const gradientId = `nura-mark-aura-${++instances}`;
  return (
    <svg
      class="brand-mark"
      data-speaking={speaking ? "true" : undefined}
      viewBox="0 0 200 200"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop class="brand-mark-stop-a" offset="0" stop-color="#B9A6E0" />
          <stop class="brand-mark-stop-b" offset="1" stop-color="#F0C9DA" />
        </linearGradient>
      </defs>
      <path d="M86 166C44 138 22 102 36 74c12-24 48-22 64 4" fill="none" stroke="#4E3A78" stroke-width="20" stroke-linecap="round" />
      <path
        class="brand-mark-aura"
        d="M114 166c42-28 64-64 50-92-12-24-48-22-64 4"
        fill="none"
        stroke={`url(#${gradientId})`}
        stroke-width="20"
        stroke-linecap="round"
      />
      <circle class="brand-mark-dot" cx="100" cy="112" r="12" fill="#4E3A78" />
    </svg>
  );
}
