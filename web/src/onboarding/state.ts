import { signal } from "@preact/signals";
import type { BiographyOut, ClosedOut, ConditionsOut, PlanOut, ProfileOut, ReviewCardOut, SettingsIn, SettingsOut } from "../api/types";
import { go } from "../flow";
import { clearProfileData } from "../offline/todayCache";
import { voice } from "../player/voice";
import { chooseProfile, profile } from "../store/session";
import { fill } from "../strings";
import type { AboutItem } from "./about";

/** Where the onboarding session is, and what it has been told so far.
 *
 *  Everything here lives in memory for as long as the page is open. None of it is written
 *  to the phone — not IndexedDB, not localStorage, not sessionStorage — because none of it
 *  is bound to a key or has an expiry: the backend holds the settings, the biography and
 *  the plan, and the screens ask it again. Closing the app mid-way loses only the place. */

export type Stage =
  /** `only`: one question of About you, from a gap card; answering it saves and goes back. */
  | { name: "about"; only?: AboutItem }
  | { name: "cloud" }
  /** `only`: one word's follow-up, reopened by a gap card; answering it goes back there. */
  | { name: "asks"; only?: string }
  | { name: "readBack" }
  | { name: "records" }
  | { name: "review"; card: ReviewCardOut }
  /** Checkpoint 3, "What it means for you" (package 7): right after "Looks right", before the
   *  sitting takes the paper in — `card` is the freshly confirmed one, corrections merged. */
  | { name: "insight"; card: ReviewCardOut }
  | { name: "questions" }
  | { name: "plan" }
  | { name: "invite" }
  /** Many photos at once (E18-01): the grid, one yes, a review card each. */
  | { name: "batch" };

export const stage = signal<Stage>({ name: "about" });
export const settings = signal<SettingsOut | null>(null);
/** About you's answers, kept until the cloud saves them with the words he tapped (one PUT). */
export const draft = signal<SettingsIn | null>(null);
/** The close: the summary in his words and the first week, for the Ready screen. */
export const closed = signal<ClosedOut | null>(null);
export const conditions = signal<ConditionsOut | null>(null);
/** The words he tapped, in the order he tapped them. */
export const picked = signal<string[]>([]);
/** His answer to each follow-up question, by word id. */
export const answers = signal<Record<string, string>>({});
export const biography = signal<BiographyOut | null>(null);
export const plan = signal<PlanOut | null>(null);
/** Where a paper goes back to once he has said yes to its card: the records step, or the
 *  Ready screen's "Do it now". */
export const returnTo = signal<"records" | "plan" | "batch">("records");
/** The paper he last added, for the "What Nura learned" card. */
export const lastPaper = signal<string | null>(null);
/** One line the Ready screen says when it comes back from an action ("They can see those parts now."). */
export const planNote = signal<string | null>(null);

export function reset(): void {
  stage.value = { name: "about" };
  settings.value = null;
  draft.value = null;
  closed.value = null;
  conditions.value = null;
  picked.value = [];
  answers.value = {};
  biography.value = null;
  plan.value = null;
  returnTo.value = "records";
  lastPaper.value = null;
  planNote.value = null;
}

/** Begin with these papers: the owner's own, just opened, or the ones a chief has just set up
 *  for someone (who then sees the caregiver density, from the standing). */
export async function startOnboarding(papers: ProfileOut): Promise<void> {
  reset();
  // As `openProfile` does: a page kept for other papers is never shown under these.
  const before = profile.value;
  if (before && before.profile_id !== papers.profile_id) {
    await clearProfileData(before.profile_id);
    voice.forget();
  }
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
  return {
    self: papers?.standing === "owner",
    name: draft.value?.preferred_name || settings.value?.preferred_name || papers?.display_name || "",
  };
}

/** The line for his own papers, or the one naming the person they are for. */
export function say(self: string, other: string): string {
  const who = whose();
  return who.self ? self : fill(other, { name: who.name });
}

