import type { PlanCardOut, PlanOut } from "../api/types";
import type { Density } from "../store/session";

/** Gaps and unlocks (E01-04, docs/gaps-and-unlocks.md): which cards the Ready screen shows.
 *  The patient sees one — the first thing Nura will ask for, and how many follow; the
 *  caregiver, who has the papers to hand, sees the whole list in order (§3). Pure
 *  (`tests/unit/plan.test.ts`). The order is the backend's: by day, then as it listed them. */
export function cardsToShow(plan: PlanOut | null, density: Density): { shown: PlanCardOut[]; after: number } {
  const cards = [...(plan?.cards ?? [])]
    .map((card, position) => ({ card, position }))
    .sort((a, b) => a.card.day.localeCompare(b.card.day) || a.position - b.position)
    .map(({ card }) => card);
  if (density === "caregiver") return { shown: cards, after: 0 };
  return { shown: cards.slice(0, 1), after: Math.max(0, cards.length - 1) };
}

/** "Do it now" opens the camera only when the backend says the gap is filled by a photo. */
export function opensCamera(card: PlanCardOut): boolean {
  return card.capture === "photo";
}
