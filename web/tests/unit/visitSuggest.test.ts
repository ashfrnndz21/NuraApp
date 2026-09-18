import { describe, expect, it } from "vitest";
import type { VisitProposalOut } from "../../src/api/types";
import { en } from "../../src/strings/en";
import { suggestionLine, suggestionWhy } from "../../src/visits/model";

function proposal(over: Partial<VisitProposalOut> = {}): VisitProposalOut {
  return {
    proposal_id: "p1",
    source: "follow_up",
    purpose: "Nura suggests you see your doctor again around Monday 2 November.",
    provider_kind: null,
    suggested_at: "2026-11-02T00:00:00Z",
    why: [{ kind: "fact", id: "f1", scope: "records" }],
    ...over,
  };
}

describe("T2's 'Nura suggests' row (app.reasoning.visits.planner, VisitSuggest.tsx)", () => {
  it("reads the backend's own words for the owner, as they are", () => {
    const one = proposal();
    expect(suggestionLine(one, true, "Pa", en)).toBe(one.purpose);
  });

  it("reads the screen's own line for a caregiver's key, by name — never the backend's 'you' line", () => {
    const one = proposal();
    const line = suggestionLine(one, false, "Pa", en);
    expect(line).not.toBe(one.purpose);
    expect(line).toContain("Pa");
    expect(line.toLowerCase()).not.toContain(" you ");
  });

  it("names the why for each of the four sources the planner reads", () => {
    expect(suggestionWhy("follow_up", en)).toBe(en.visitSuggest.followUpWhy);
    expect(suggestionWhy("medicine_review", en)).toBe(en.visitSuggest.medicineReviewWhy);
    expect(suggestionWhy("test_coming", en)).toBe(en.visitSuggest.testComingWhy);
    expect(suggestionWhy("screening_due", en)).toBe(en.visitSuggest.screeningDueWhy);
  });
});
