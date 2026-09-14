import { describe, expect, it } from "vitest";
import type { PlanOut, PromptOut } from "../../src/api/types";
import { cardsToShow, invites, opensCamera, opensFile, pending, tapsCloud, tapsSetting } from "../../src/onboarding/plan";

const prompt = (gap: string, due: string, capture: PromptOut["capture"] = "photo", status: PromptOut["status"] = "pending"): PromptOut => ({
  prompt: gap,
  day: 1,
  tier: 1,
  capture,
  word: null,
  deferred: 0,
  due_at: due,
  due_local: due,
  status,
  done_at: null,
  done_by_fact_id: null,
  skipped_at: null,
  headline: "h",
  line: "l",
  action: "a",
});

const plan = (prompts: PromptOut[], stopped = false): PlanOut => ({
  plan_id: "pl1",
  profile_id: "p1",
  biography_id: null,
  created_at: "2026-09-14T02:00:00Z",
  first_day: "2026-09-15",
  breakfast_time: "07:30",
  timezone: "Asia/Singapore",
  stopped,
  stopped_because: [],
  prompts,
  due: [],
});

const A = "2026-09-15T23:30:00Z";
const B = "2026-09-16T23:30:00Z";
const C = "2026-09-17T23:30:00Z";

describe("the first week on the Ready screen", () => {
  it("shows the patient the next prompt still to do, soonest first, and how many follow", () => {
    const week = plan([prompt("insurance", C), prompt("medicines", A, "photo", "done"), prompt("bp_numbers", B), prompt("next_visit", A, "photo", "skipped")]);
    expect(pending(week).map((each) => each.prompt)).toEqual(["bp_numbers", "insurance"]);
    const { shown, after } = cardsToShow(week, "patient");
    expect(shown.map((each) => each.prompt)).toEqual(["bp_numbers"]);
    expect(after).toBe(1);
  });

  it("shows the caregiver every prompt still to do, in order", () => {
    const { shown, after } = cardsToShow(plan([prompt("insurance", C), prompt("bp_numbers", B)]), "caregiver");
    expect(shown.map((each) => each.prompt)).toEqual(["bp_numbers", "insurance"]);
    expect(after).toBe(0);
  });

  it("keeps the backend's order for the same moment", () => {
    expect(pending(plan([prompt("b", A), prompt("a", A)])).map((each) => each.prompt)).toEqual(["b", "a"]);
  });

  it("shows nothing once the week has stopped, or before it has come", () => {
    expect(cardsToShow(plan([prompt("medicines", A)], true), "patient")).toEqual({ shown: [], after: 0 });
    expect(cardsToShow(null, "patient")).toEqual({ shown: [], after: 0 });
  });

  it("opens what the backend says fills the gap", () => {
    expect(opensCamera(prompt("medicines", A, "photo"))).toBe(true);
    expect(opensFile(prompt("cholesterol_result", A, "pdf"))).toBe(true);
    expect(opensCamera(prompt("cholesterol_result", A, "pdf"))).toBe(false);
    const about = (word: string | null) => ({ ...prompt("allergy_which", A, "tap"), word });
    expect(tapsCloud(about("Allergic to a medicine"))).toBe(true);
    expect(tapsSetting(about("Allergic to a medicine"))).toBe(false);
    expect(tapsSetting(about(null))).toBe(true);
    expect(tapsCloud(about(null))).toBe(false);
  });

  it("goes to the invite only on his own papers, since the consent is his own yes", () => {
    const invite = prompt("someone_to_see", A, "invite");
    expect(invites(invite, "owner")).toBe(true);
    expect(invites(invite, "steward")).toBe(false);
    expect(invites(invite, "holder")).toBe(false);
    expect(invites(prompt("insurance", A, "photo"), "owner")).toBe(false);
  });
});
