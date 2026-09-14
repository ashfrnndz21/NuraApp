import { describe, expect, it } from "vitest";
import type { PlanCardOut, PlanOut } from "../../src/api/types";
import { asksWord, cardsToShow, invites, opensCamera } from "../../src/onboarding/plan";

const card = (gap_id: string, day: string, capture: PlanCardOut["capture"] = "photo"): PlanCardOut => ({
  gap_id,
  day,
  tier: 1,
  missing: "m",
  unlock: "u",
  action: "a",
  capture,
  state_id: "s1",
  source: "src",
  deferred: 0,
});

const plan = (cards: PlanCardOut[]): PlanOut => ({ profile_id: "p1", state_id: "s1", cards });

describe("gaps and unlocks", () => {
  it("shows the patient one card — the first by day — and how many follow", () => {
    const { shown, after } = cardsToShow(plan([card("ins", "2026-09-17"), card("meds", "2026-09-15"), card("bpv", "2026-09-16")]), "patient");
    expect(shown.map((each) => each.gap_id)).toEqual(["meds"]);
    expect(after).toBe(2);
  });

  it("shows the caregiver the whole list, in order", () => {
    const { shown, after } = cardsToShow(plan([card("ins", "2026-09-17"), card("meds", "2026-09-15")]), "caregiver");
    expect(shown.map((each) => each.gap_id)).toEqual(["meds", "ins"]);
    expect(after).toBe(0);
  });

  it("keeps the backend's order for cards on the same day", () => {
    const { shown } = cardsToShow(plan([card("b", "2026-09-15"), card("a", "2026-09-15")]), "caregiver");
    expect(shown.map((each) => each.gap_id)).toEqual(["b", "a"]);
  });

  it("shows nothing, and counts nothing, before the plan has come", () => {
    expect(cardsToShow(null, "patient")).toEqual({ shown: [], after: 0 });
  });

  it("opens the camera only for a gap a photo fills", () => {
    expect(opensCamera(card("meds", "2026-09-15", "photo"))).toBe(true);
    expect(opensCamera(card("all", "2026-09-15", "tap"))).toBe(false);
    expect(opensCamera(card("fam", "2026-09-15", "none"))).toBe(false);
  });
});

describe("the gap card's other actions", () => {
  it("reopens the follow-up question of the word a tap gap names", () => {
    expect(asksWord({ ...card("all", "2026-09-15", "tap"), word: "drug_all" })).toBe("drug_all");
    expect(asksWord({ ...card("all", "2026-09-15", "tap"), word: null })).toBeNull();
    expect(asksWord(card("meds", "2026-09-15", "photo"))).toBeNull();
  });

  it("goes to the invite only on his own papers, since the consent is his own yes", () => {
    const fam = card("fam", "2026-09-20", "invite");
    expect(invites(fam, "owner")).toBe(true);
    expect(invites(fam, "steward")).toBe(false);
    expect(invites(fam, "holder")).toBe(false);
    expect(invites(card("ins", "2026-09-20", "photo"), "owner")).toBe(false);
  });
});
