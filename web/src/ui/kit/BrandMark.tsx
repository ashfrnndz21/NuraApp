import type { JSX } from "preact";

/** The mark (docs/brand/BRAND.md): two strokes that meet at the top and never close at the
 *  bottom — plum on the left, the aura on the right — and the dot inside. Fixed; drawn from
 *  `docs/brand/nura-mark.svg` as-is, at the header's size. Decorative: the app's name is said
 *  by the page, not by the picture. */
export function BrandMark({ size = 32 }: { size?: number }): JSX.Element {
  return (
    <svg class="brand-mark" viewBox="0 0 200 200" width={size} height={size} aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="nura-mark-aura" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#B9A6E0" />
          <stop offset="1" stop-color="#F0C9DA" />
        </linearGradient>
      </defs>
      <path d="M86 166C44 138 22 102 36 74c12-24 48-22 64 4" fill="none" stroke="#4E3A78" stroke-width="20" stroke-linecap="round" />
      <path d="M114 166c42-28 64-64 50-92-12-24-48-22-64 4" fill="none" stroke="url(#nura-mark-aura)" stroke-width="20" stroke-linecap="round" />
      <circle cx="100" cy="112" r="12" fill="#4E3A78" />
    </svg>
  );
}
