import { signal } from "@preact/signals";

/** `#/blueprint-kit` (P1 of the redesign): a review-only gallery of the dusk-glass kit
 *  (`web/src/ui/kit`), not part of the app's own navigation (docs/product-reset.md's "no URL
 *  routing" is still true for the real app — this is the one deliberate exception, and it never
 *  reaches a real screen). Kept to its own tiny module rather than `flow.ts`'s `Screen` union, so
 *  nothing about the real app's routing has to know this exists. */
export const hash = signal(typeof location === "undefined" ? "" : location.hash);

if (typeof window !== "undefined") {
  window.addEventListener("hashchange", () => {
    hash.value = location.hash;
  });
}

export function isBlueprintKitRoute(): boolean {
  return hash.value === "#/blueprint-kit";
}
