import { describe, expect, it } from "vitest";
import type { InsightOut, PaperInsightOut, ReviewCardOut, ReviewFieldOut } from "../../src/api/types";
import {
  hasQuestionSelection,
  initialPaperInsightState,
  initialQuestionSelection,
  paperInsightHasNothingToAsk,
  paperInsightStatusText,
  standoutRows,
  toggleQuestionSelection,
  whereKept,
  withPaperInsightReport,
  withPaperInsightStep,
} from "../../src/health/paperInsight";
import { en } from "../../src/strings/en";

/** Checkpoint 3, "What it means for you" (package 7): the pure view logic `screens/Insight.tsx`
 *  renders from — the stream's own accumulator, the selection the person makes among the
 *  questions offered, and "what stands out" off the confirmed card's own printed ranges. No
 *  component, no fetch: every case here is a plain function call on plain data. */

const field = (field_id: string, value: unknown, range: ReviewFieldOut["range"], position = 0): ReviewFieldOut => ({
  field_id,
  position,
  subject: "lipid_panel",
  attribute: field_id,
  value,
  unit: "mmol/L",
  confidence: 0.95,
  needs_confirm: false,
  unreadable: false,
  prompt: null,
  page: null,
  range,
  label_on_paper: null,
  state: "proposed",
  corrected_value: null,
  fact_id: null,
});

const card = (fields: ReviewFieldOut[]): ReviewCardOut => ({
  card_id: "c1",
  profile_id: "p1",
  artifact_id: "a1",
  document_kind: "lab_report",
  document_date: "2026-09-12",
  asked_as: null,
  source: null,
  notice: null,
  high_risk_class: null,
  created_at: "2026-09-12T00:00:00Z",
  confirmed_at: "2026-09-12T00:01:00Z",
  fields,
});

const question = (insight_id: string, text: string): InsightOut => ({
  insight_id,
  kind: "check",
  text,
  ask_who: "doctor",
  evidence: [],
  why_plain: "This is compared only with the range printed on this paper.",
  confidence: "worth_a_look",
});

const report = (questions: InsightOut[]): PaperInsightOut => ({
  report_id: "r1",
  generated_at: "2026-09-12T00:02:00Z",
  boundary: ["This is not a doctor's advice."],
  headline: questions.length > 0 ? "Here is what is worth asking about this paper." : "Nothing on this paper looks worth a question right now.",
  looked_at: [{ kind: "artifact", id: "a1", label: "this paper" }],
  questions,
  withheld: [],
});

describe("paperInsight: the stream accumulator", () => {
  it("appends steps in order, never reordering or dropping one", () => {
    let state = withPaperInsightStep(initialPaperInsightState, "paper", "Looking at this paper.");
    state = withPaperInsightStep(state, "medicines", "Looking at your medicines.");
    expect(state.steps.map((s) => s.label)).toEqual(["Looking at this paper.", "Looking at your medicines."]);
    expect(state.report).toBeNull();
  });

  it("keeps every step once the report lands — never cleared, so 'what arrived stays' on a later failure", () => {
    let state = withPaperInsightStep(initialPaperInsightState, "paper", "Looking at this paper.");
    const finished = report([question("q1", "The cholesterol on this paper is outside the range printed on it.")]);
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

describe("paperInsight: what stands out on the paper", () => {
  it("keeps only the rows outside the paper's own printed range, in the order the paper prints them", () => {
    const rows = standoutRows(
      card([
        field("ldl", 4.2, { low: 1.5, high: 3.4, text: "1.5-3.4" }, 2),
        field("hdl", 1.4, { low: 1.0, high: null, text: ">1.0" }, 1),
        field("triglycerides", 0.6, { low: null, high: 1.7, text: "<1.7" }, 0),
      ]),
      en,
      "en-SG",
    );
    expect(rows.map((r) => r.fieldId)).toEqual(["ldl"]);
    expect(rows[0]!.status).toBe("above");
  });

  it("a paper with no parsable range has nothing to stand out — never guessed", () => {
    const rows = standoutRows(card([field("triglycerides", 0.6, null)]), en, "en-SG");
    expect(rows).toEqual([]);
  });

  it("a value exactly on the bound is in range, never flagged (`rangeStatus`'s own inclusive edge)", () => {
    const rows = standoutRows(card([field("ldl", 3.4, { low: 1.5, high: 3.4, text: "1.5-3.4" })]), en, "en-SG");
    expect(rows).toEqual([]);
  });
});

describe("paperInsight: which questions the person keeps", () => {
  it("every question is pre-selected (the blueprint's own card: nothing struck out by default)", () => {
    const selection = initialQuestionSelection([question("q1", "…"), question("q2", "…")]);
    expect(selection.has("q1")).toBe(true);
    expect(selection.has("q2")).toBe(true);
    expect(hasQuestionSelection(selection)).toBe(true);
  });

  it("toggling a row takes it out of the selection, and back in on a second tap", () => {
    let selection = initialQuestionSelection([question("q1", "…")]);
    selection = toggleQuestionSelection(selection, "q1");
    expect(selection.has("q1")).toBe(false);
    selection = toggleQuestionSelection(selection, "q1");
    expect(selection.has("q1")).toBe(true);
  });

  it("unchecking every row leaves nothing to keep — 'Keep these questions' is stopped here, on the client, rather than telling him something was kept when nothing he still wanted was singled out", () => {
    let selection = initialQuestionSelection([question("q1", "…")]);
    selection = toggleQuestionSelection(selection, "q1");
    expect(hasQuestionSelection(selection)).toBe(false);
  });
});

describe("paperInsight: where 'Keep these questions' filed them", () => {
  it("reads `filed` straight off the response — never a guess, and never a visit named the response itself did not name", () => {
    expect(whereKept({ filed: "visit" })).toEqual({ kind: "visit" });
    expect(whereKept({ filed: "unfiled" })).toEqual({ kind: "unfiled" });
  });
});
