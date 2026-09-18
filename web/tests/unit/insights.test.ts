import { describe, expect, it } from "vitest";
import type { InsightOut, InsightsReportOut } from "../../src/api/types";
import { confidenceWordKey, headlineInsight, insightsTraceSteps, sectionsFor, SECTION_ORDER } from "../../src/health/insights";

function insight(overrides: Partial<InsightOut> = {}): InsightOut {
  return {
    insight_id: "i1",
    kind: "trend",
    text: "Your blood pressure has been a little higher this week.",
    ask_who: "Dr Tan",
    evidence: [{ id: "e1", kind: "fact", label: "Your blood pressure book" }],
    why_plain: "It read higher on three of the last four mornings.",
    confidence: "sure",
    ...overrides,
  };
}

function report(sections: InsightsReportOut["sections"]): InsightsReportOut {
  return {
    report_id: "r1",
    generated_at: "2026-09-18T02:00:00Z",
    week_of: "2026-09-14T00:00:00Z",
    boundary: ["Nura read this from your papers.", "This is not a doctor's advice.", "Ask your doctor."],
    sections,
  };
}

describe("the weekly report's view logic", () => {
  it("shows every section the fixed order names, in that order, each present or withheld", () => {
    const views = sectionsFor(report([{ key: "what_changed", title: "What changed", insights: [insight()] }]));
    expect(views.map((v) => v.key)).toEqual(SECTION_ORDER);
    expect(views[0]).toEqual({ key: "what_changed", state: "present", title: "What changed", insights: [insight()] });
    expect(views[1]).toEqual({ key: "worth_a_look", state: "withheld" });
  });

  it("a section present with no insights is not withheld: Nura looked and found nothing", () => {
    const views = sectionsFor(report([{ key: "screenings_due", title: "Screenings due", insights: [] }]));
    const screenings = views.find((v) => v.key === "screenings_due");
    expect(screenings).toEqual({ key: "screenings_due", state: "present", title: "Screenings due", insights: [] });
  });

  it("a section under a key the fixed order does not name is still shown, never dropped", () => {
    const views = sectionsFor(report([{ key: "a_new_section", title: "Something new", insights: [] }]));
    expect(views.at(-1)).toEqual({ key: "a_new_section", state: "present", title: "Something new", insights: [] });
  });

  it("leads with the first insight of the first section that has one, in the fixed order", () => {
    const worthALook = insight({ insight_id: "wal", text: "Worth a look line." });
    const whatChanged = insight({ insight_id: "wc", text: "What changed line." });
    const found = headlineInsight(
      report([
        { key: "worth_a_look", title: "Worth a look", insights: [worthALook] },
        { key: "what_changed", title: "What changed", insights: [whatChanged] },
      ]),
    );
    expect(found?.insight_id).toBe("wc");
  });

  it("has no headline when every section is withheld or empty", () => {
    expect(headlineInsight(report([{ key: "what_changed", title: "What changed", insights: [] }]))).toBeNull();
    expect(headlineInsight(report([]))).toBeNull();
  });

  it("marks every trace step done but the one still streaming", () => {
    const steps = insightsTraceSteps([
      { key: "meds", label: "Reading your medicines" },
      { key: "labs", label: "Reading your blood tests" },
    ]);
    expect(steps).toEqual([
      { key: "meds", text: "Reading your medicines", done: true },
      { key: "labs", text: "Reading your blood tests", done: false },
    ]);
  });

  it("maps the backend's confidence word to the catalogue's own key, worth_a_look aside", () => {
    expect(confidenceWordKey("sure")).toBe("sure");
    expect(confidenceWordKey("likely")).toBe("likely");
    expect(confidenceWordKey("worth_a_look")).toBe("worthALook");
  });
});
