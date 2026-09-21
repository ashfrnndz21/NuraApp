import { describe, expect, it } from "vitest";
import type { AppointmentOut, InsightOut, PaperInsightOut } from "../../src/api/types";
import {
  cardVisitOf,
  initialPaperInsightState,
  lookedAtLabels,
  paperInsightHasNothingToAsk,
  paperInsightStatusText,
  whereKept,
  withPaperInsightReport,
  withPaperInsightStep,
} from "../../src/health/paperInsight";

/** Checkpoint 3, "What it means for you" (package 7): the pure view logic `screens/Insight.tsx`
 *  renders from — the stream's own accumulator, what the engine really read, the card's own
 *  title, and where "Keep these for my visit" filed the questions. No component, no fetch:
 *  every case here is a plain function call on plain data. */

const question = (insight_id: string, text: string): InsightOut => ({
  insight_id,
  kind: "check",
  text,
  ask_who: "doctor",
  evidence: [],
  why_plain: "This is compared only with the range printed on this paper.",
  confidence: "worth_a_look",
});

const report = (questions: InsightOut[], lookedAt: PaperInsightOut["looked_at"] = [{ kind: "artifact", id: "a1", label: "this paper" }]): PaperInsightOut => ({
  report_id: "r1",
  generated_at: "2026-09-12T00:02:00Z",
  boundary: ["This is not a doctor's advice."],
  headline: questions.length > 0 ? "Here is what I would ask." : "Nothing on this paper looks worth a question right now.",
  looked_at: lookedAt,
  questions,
  withheld: [],
});

const visit = (doctor: string | null, scheduled_at = "2026-09-25T10:30:00Z"): Pick<AppointmentOut, "doctor" | "scheduled_at"> => ({ doctor, scheduled_at });

describe("paperInsight: the stream accumulator", () => {
  it("appends steps in order, never reordering or dropping one", () => {
    let state = withPaperInsightStep(initialPaperInsightState, "paper", "Looking at this paper.");
    state = withPaperInsightStep(state, "medicines", "Looking at your medicines.");
    expect(state.steps.map((s) => s.label)).toEqual(["Looking at this paper.", "Looking at your medicines."]);
    expect(state.report).toBeNull();
  });

  it("keeps every step once the report lands — never cleared, so 'what arrived stays' on a later failure", () => {
    let state = withPaperInsightStep(initialPaperInsightState, "paper", "Looking at this paper.");
    const finished = report([question("q1", "My bad cholesterol is above the range on this paper. What does that mean for me?")]);
    state = withPaperInsightReport(state, finished);
    expect(state.steps).toHaveLength(1);
    expect(state.report).toBe(finished);
  });

  it("status text is the newest step's own label — never an accumulating checklist, never a fixed word once one real step has arrived", () => {
    let state = withPaperInsightStep(initialPaperInsightState, "paper", "Looking at this paper.");
    state = withPaperInsightStep(state, "medicines", "Looking at your medicines.");
    expect(paperInsightStatusText(state, "Nura is looking.")).toBe("Looking at your medicines.");
  });

  it("status text falls back to the caller's own words before the first real step has arrived", () => {
    expect(paperInsightStatusText(initialPaperInsightState, "Nura is looking.")).toBe("Nura is looking.");
  });

  it("nothing to ask is read straight off the report's own questions — never guessed from the headline", () => {
    expect(paperInsightHasNothingToAsk(report([]))).toBe(true);
    expect(paperInsightHasNothingToAsk(report([question("q1", "…")]))).toBe(false);
  });
});

describe("paperInsight: what the engine really looked at", () => {
  it("reads the backend's own labels, in the order the stream gave them", () => {
    const withThree = report([], [
      { kind: "artifact", id: "a1", label: "this paper" },
      { kind: "medicines", id: "m1,m2", label: "2 of your medicines" },
      { kind: "appointment", id: "v1", label: "your next visit" },
    ]);
    expect(lookedAtLabels(withThree)).toEqual(["this paper", "2 of your medicines", "your next visit"]);
  });

  it("names nothing when the response names nothing — never invented", () => {
    expect(lookedAtLabels(report([], []))).toEqual([]);
  });
});

describe("paperInsight: the card's own title", () => {
  it("names the next visit's real doctor and date when both are there", () => {
    expect(cardVisitOf([visit("Dr Lim")])).toEqual({ kind: "named", doctor: "Dr Lim", scheduledAt: "2026-09-25T10:30:00Z" });
  });

  it("falls back to the generic title with no visit booked", () => {
    expect(cardVisitOf([])).toEqual({ kind: "generic" });
  });

  it("falls back to the generic title when the next visit has no doctor named yet — never a guessed name", () => {
    expect(cardVisitOf([visit(null)])).toEqual({ kind: "generic" });
    expect(cardVisitOf([visit("")])).toEqual({ kind: "generic" });
    expect(cardVisitOf([visit("   ")])).toEqual({ kind: "generic" });
  });

  it("takes the soonest visit — the first in the list, the same order `nura.appointments` already answers in", () => {
    expect(cardVisitOf([visit("Dr Lim", "2026-09-25T10:30:00Z"), visit("Dr Tan", "2026-10-01T09:00:00Z")])).toEqual({
      kind: "named",
      doctor: "Dr Lim",
      scheduledAt: "2026-09-25T10:30:00Z",
    });
  });
});

describe("paperInsight: where 'Keep these for my visit' filed them", () => {
  it("reads `filed` straight off the response — never a guess, and never a visit named the response itself did not name", () => {
    expect(whereKept({ filed: "visit" })).toEqual({ kind: "visit" });
    expect(whereKept({ filed: "unfiled" })).toEqual({ kind: "unfiled" });
  });
});
