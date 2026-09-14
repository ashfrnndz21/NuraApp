import { signal } from "@preact/signals";
import type { BiographyOut, ConditionsOut, PlanOut, ProfileOut, ReviewCardOut, SettingsOut } from "../api/types";
import { go } from "../flow";
import { clearProfileData } from "../offline/todayCache";
import { chooseProfile, profile } from "../store/session";
import { fill } from "../strings";

/** Where the onboarding session is, and what it has been told so far.
 *
 *  Everything here lives in memory for as long as the page is open. None of it is written
 *  to the phone — not IndexedDB, not localStorage, not sessionStorage — because none of it
 *  is bound to a key or has an expiry: the backend holds the settings, the biography and
 *  the plan, and the screens ask it again. Closing the app mid-way loses only the place. */

export type Stage =
  | { name: "about" }
  | { name: "cloud" }
  | { name: "asks" }
  | { name: "readBack" }
  | { name: "records" }
  | { name: "review"; card: ReviewCardOut }
  | { name: "questions" }
  | { name: "plan" };

export const stage = signal<Stage>({ name: "about" });
export const settings = signal<SettingsOut | null>(null);
export const conditions = signal<ConditionsOut | null>(null);
/** The words he tapped, in the order he tapped them. */
export const picked = signal<string[]>([]);
/** His answer to each follow-up question, by word id. */
export const answers = signal<Record<string, string>>({});
export const biography = signal<BiographyOut | null>(null);
export const plan = signal<PlanOut | null>(null);
/** Where a paper goes back to once he has said yes to its card: the records step, or the
 *  Ready screen's "Do it now". */
export const returnTo = signal<"records" | "plan">("records");
/** The paper he last added, for the "What Nura learned" card. */
export const lastPaper = signal<string | null>(null);

export function reset(): void {
  stage.value = { name: "about" };
  settings.value = null;
  conditions.value = null;
  picked.value = [];
  answers.value = {};
  biography.value = null;
  plan.value = null;
  returnTo.value = "records";
  lastPaper.value = null;
}

/** Begin with these papers: the owner's own, just opened, or the ones a chief has just set up
 *  for someone (who then sees the caregiver density, from the standing). */
export async function startOnboarding(papers: ProfileOut): Promise<void> {
  reset();
  // As `openProfile` does: a page kept for other papers is never shown under these.
  const before = profile.value;
  if (before && before.profile_id !== papers.profile_id) await clearProfileData(before.profile_id);
  await chooseProfile(papers);
  go({ name: "onboarding" });
}

export function to(next: Stage): void {
  stage.value = next;
  if (typeof window !== "undefined") window.scrollTo(0, 0);
}

export function finish(): void {
  reset();
  go({ name: "today" });
}

/** Whose papers these are, for the lines that say "you" or name him. */
export function whose(): { self: boolean; name: string } {
  const papers = profile.value;
  return { self: papers?.standing === "owner", name: settings.value?.preferred_name || papers?.display_name || "" };
}

/** The line for his own papers, or the one naming the person they are for. */
export function say(self: string, other: string): string {
  const who = whose();
  return who.self ? self : fill(other, { name: who.name });
}

