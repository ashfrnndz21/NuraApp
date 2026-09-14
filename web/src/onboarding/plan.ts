import type { PlanOut, PromptOut } from "../api/types";
import type { Density } from "../store/session";

/** Gaps and unlocks on the Ready screen (E01-04, #117's first week): which prompts show. The
 *  patient sees one — the next still to do — and how many follow; the caregiver sees every one
 *  still to do (docs/gaps-and-unlocks.md §3). Pure (`tests/unit/plan.test.ts`). */

/** The prompts still to do, soonest first; the backend's order for the same moment. */
export function pending(plan: PlanOut | null): PromptOut[] {
  if (!plan || plan.stopped) return [];
  return plan.prompts
    .map((prompt, position) => ({ prompt, position }))
    .filter(({ prompt }) => prompt.status === "pending")
    .sort((a, b) => a.prompt.due_at.localeCompare(b.prompt.due_at) || a.position - b.position)
    .map(({ prompt }) => prompt);
}

export function cardsToShow(plan: PlanOut | null, density: Density): { shown: PromptOut[]; after: number } {
  const open = pending(plan);
  if (density === "caregiver") return { shown: open, after: 0 };
  return { shown: open.slice(0, 1), after: Math.max(0, open.length - 1) };
}

/** What "Do it now" opens, by how the backend says the gap is filled. */
export const opensCamera = (prompt: PromptOut): boolean => prompt.capture === "photo";
export const opensFile = (prompt: PromptOut): boolean => prompt.capture === "pdf";
/** A tap gap is filled by a tap on the cloud (E01 has no follow-up question for it yet). */
export const tapsCloud = (prompt: PromptOut): boolean => prompt.capture === "tap";

/** The invite is his own yes (the consent route takes the owner's), so only on his own papers. */
export function invites(prompt: PromptOut, standing: string | undefined): boolean {
  return prompt.capture === "invite" && standing === "owner";
}
