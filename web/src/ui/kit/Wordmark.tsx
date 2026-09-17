import type { JSX } from "preact";
import { BrandMark } from "./BrandMark";

/** The wordmark: the heart mark and "Nura" in the serif display face. `as="h1"` where it is the
 *  page's name (Welcome); else a plain span, decorative beside the page's own heading. */
export function Wordmark({ name, size = "small", as = "span", mark = true }: { name: string; size?: "small" | "large"; as?: "span" | "h1"; mark?: boolean }): JSX.Element {
  const Tag = as;
  return (
    <Tag class={`wordmark ${size}`}>
      {mark && <BrandMark size={size === "large" ? 44 : 28} />}
      <span class="wordmark-word">{name}</span>
    </Tag>
  );
}
