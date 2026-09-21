import { describe, expect, it } from "vitest";
import type { InsightOut, InsightsReportOut, InsightsReportSummaryOut } from "../../src/api/types";
import { ANALYST_STREAM_IDLE, analystStreamReducer, confidenceWordKey, headlineInsight, insightsTraceSteps, pastReportsNewestFirst, sectionsFor, SECTION_ORDER } from "../../src/health/insights";
import { ringHasNothingToCount } from "../../src/health/model";

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

// --- the Health Analyst screen's own live stream (package 10) ----------------------------------

describe("the analyst stream reducer: stages -> headline -> sections, never two truths at once", () => {
  it("starts working with no status text until the first real stage lands", () => {
    const working = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "start" });
    expect(working).toEqual({ phase: "working", statusText: "" });
  });

  it("ONE status line, replaced in place, one real stage after another — never an accumulating list", () => {
    let state = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "start" });
    state = analystStreamReducer(state, { type: "step", label: "Reading your records" });
    expect(state).toEqual({ phase: "working", statusText: "Reading your records" });
    state = analystStreamReducer(state, { type: "step", label: "Reading your blood pressure book" });
    // The line is REPLACED, not appended: only the newest stage's own text survives.
    expect(state).toEqual({ phase: "working", statusText: "Reading your blood pressure book" });
  });

  it("a stray step after the stream already settled never reopens a finished or failed screen", () => {
    const done = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "report", report: report([]) });
    expect(analystStreamReducer(done, { type: "step", label: "late" })).toBe(done);
  });

  it("the finished report carries the last real stage's line forward, for the headline that follows it", () => {
    let state = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "start" });
    state = analystStreamReducer(state, { type: "step", label: "Reading what you pay" });
    const finished = analystStreamReducer(state, { type: "report", report: report([{ key: "what_changed", title: "What changed", insights: [insight()] }]) });
    expect(finished.phase).toBe("done");
    expect(finished).toMatchObject({ statusText: "Reading what you pay" });
  });

  it("a report loaded straight from the wire (no stream just run) settles calmly, with no status text to show", () => {
    const loaded = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "report", report: report([]) });
    expect(loaded).toEqual({ phase: "done", report: report([]), statusText: "" });
  });

  it("a refusal or a dropped connection mid-stream keeps whatever the last real stage said — what arrived stays", () => {
    let state = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "start" });
    state = analystStreamReducer(state, { type: "step", label: "Reading your medicines" });
    const failed = analystStreamReducer(state, { type: "error", message: "unreachable" });
    expect(failed).toEqual({ phase: "error", statusText: "Reading your medicines", message: "unreachable" });
  });

  it("a failure before any stage ever arrived has nothing to keep", () => {
    const failed = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "error", message: "unreachable" });
    expect(failed).toEqual({ phase: "error", statusText: "", message: "unreachable" });
  });

  it("'not enough data' is not a distinct refusal: a real report whose sections are all present and empty still reaches done, and each section says so on its own (sectionEmpty)", () => {
    const empty = report([
      { key: "what_changed", title: "What changed", insights: [] },
      { key: "worth_a_look", title: "Worth a look", insights: [] },
    ]);
    const state = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "report", report: empty });
    expect(state.phase).toBe("done");
    const views = sectionsFor(empty);
    expect(views.filter((v) => v.state === "present" && v.insights.length === 0).length).toBeGreaterThan(0);
  });

  it("reset returns to idle", () => {
    const working = analystStreamReducer(ANALYST_STREAM_IDLE, { type: "start" });
    expect(analystStreamReducer(working, { type: "reset" })).toEqual(ANALYST_STREAM_IDLE);
  });
});

describe("the week ring's empty-state logic (package 10)", () => {
  it("a fresh profile with no active medicines has nothing to count", () => {
    expect(ringHasNothingToCount({ total: 0 })).toBe(true);
  });

  it("a ring kind with no fixed total (check_ins) counts as nothing to show either", () => {
    expect(ringHasNothingToCount({ total: null })).toBe(true);
  });

  it("a real total draws the ring as usual", () => {
    expect(ringHasNothingToCount({ total: 14 })).toBe(false);
    expect(ringHasNothingToCount({ total: 5 })).toBe(false);
  });
});

describe("past reports, newest first (package 10)", () => {
  const summary = (id: string, generatedAt: string): InsightsReportSummaryOut => ({ report_id: id, generated_at: generatedAt, week_of: "2026-09-14" });

  it("sorts by generated_at, newest first", () => {
    const rows = [summary("a", "2026-09-01T00:00:00Z"), summary("b", "2026-09-15T00:00:00Z"), summary("c", "2026-09-08T00:00:00Z")];
    expect(pastReportsNewestFirst(rows).map((r) => r.report_id)).toEqual(["b", "c", "a"]);
  });

  it("breaks a tie under a frozen clock deterministically, never by the wire's own arbitrary order", () => {
    const rows = [summary("a", "2026-09-15T00:00:00Z"), summary("b", "2026-09-15T00:00:00Z")];
    const sorted = pastReportsNewestFirst(rows);
    expect(sorted.map((r) => r.report_id)).toEqual(["b", "a"]);
  });

  it("never mutates the array it is given", () => {
    const rows = [summary("a", "2026-09-01T00:00:00Z"), summary("b", "2026-09-15T00:00:00Z")];
    const original = [...rows];
    pastReportsNewestFirst(rows);
    expect(rows).toEqual(original);
  });
});
