import type { AboutItem } from "./about";
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
/** The tap gaps the settings fill: the one question of About you, then back to the week.
 *  Which medicine he is allergic to has no route to write it yet (#117), so that card has
 *  Later only — a tap on the cloud's word would close nothing. */
const SETTING_GAPS: Readonly<Record<string, AboutItem>> = { meal_times: "breakfast" };
export const tapsSetting = (prompt: PromptOut): AboutItem | null =>
  prompt.capture === "tap" ? (SETTING_GAPS[prompt.prompt] ?? null) : null;

/** The invite is his own yes (the consent route takes the owner's), so only on his own papers. */
export function invites(prompt: PromptOut, standing: string | undefined): boolean {
  return prompt.capture === "invite" && standing === "owner";
}
