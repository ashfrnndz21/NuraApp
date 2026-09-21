import { describe, expect, it, vi } from "vitest";
import type { InsightOut, InsightsReportOut } from "../../src/api/types";
import { insightsTraceSteps } from "../../src/health/insights";
import { InsightsCard } from "../../src/screens/Health";
import { InsightRow, ReportBody, SectionCard } from "../../src/screens/Insights";
import { stringsFor } from "../../src/strings";
import { StepTrace } from "../../src/ui/kit";
import { all, byTestId, hasClass, render, text } from "./ui/render";

/** The plain reading of a `SoftText` line: its own `.sr-only` span, never the word-by-word
 *  spans beside it — reading the whole subtree would double the text (each word appears once
 *  in the screen-reader span and again, unspaced, in its own animated span). The same rule the
 *  e2e specs keep with Playwright's `.locator(".sr-only")` (package 10). */
function softText(nodes: ReturnType<typeof all>): string {
  return text(all(nodes, hasClass("sr-only")));
}

const en = stringsFor("en");

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

describe("the weekly report screen, drawn from the backend's own words", () => {
  it("the trace shows the newest real step through one status line, then gives way to the report", () => {
    const steps = insightsTraceSteps([
      { key: "meds", label: "Reading your medicines" },
      { key: "labs", label: "Reading your blood tests" },
    ]);
    const trace = render(<StepTrace steps={steps} working="Nura is looking at this week." testId="insights-trace" />);
    // ONE line, the newest step reported — never an accumulating checklist
    // (docs/design/experience-blueprint.html think()).
    expect(text(trace)).toContain("Reading your blood tests");
    expect(text(trace)).not.toContain("Nura is looking at this week.");
    expect(all(trace, (el) => el.type === "li")).toHaveLength(0);

    // Before any step has arrived, the caller's own "working" line still shows, through the
    // same one status line.
    const before = render(<StepTrace steps={[]} working="Nura is looking at this week." testId="insights-trace" />);
    expect(text(before)).toContain("Nura is looking at this week.");

    // Once the stream's last event lands, the screen swaps the trace for the finished report:
    // the same backend-shaped data, drawn by `ReportBody`, never both on screen together.
    const written = report([{ key: "what_changed", title: "What changed", insights: [insight()] }]);
    const finished = render(<ReportBody report={written} s={en} name="Pa" askingId={null} askedIds={new Set()} onAsk={() => {}} hasNextVisit locale="en-SG" />);
    expect(text(finished)).toContain("Your blood pressure has been a little higher this week.");
  });

  it("a withheld section says so, by name, instead of vanishing off the report", () => {
    const tree = render(
      <SectionCard section={{ key: "what_you_pay", state: "withheld" }} s={en} name="Pa" askingId={null} askedIds={new Set()} onAsk={() => {}} hasNextVisit />,
    );
    expect(text(tree)).toContain("What you pay");
    expect(text(tree)).toContain("Pa");
    expect(text(tree)).not.toContain("undefined");
  });

  it("a section Nura looked at and found nothing to say is present, not withheld, and says so", () => {
    const tree = render(
      <SectionCard
        section={{ key: "screenings_due", state: "present", title: "Screenings due", insights: [] }}
        s={en}
        name="Pa"
        askingId={null}
        askedIds={new Set()}
        onAsk={() => {}}
        hasNextVisit
      />,
    );
    expect(text(tree)).toContain("There is nothing here this week.");
  });

  it("boundary lines end the report, after every section", () => {
    const written = report([{ key: "what_changed", title: "What changed", insights: [] }]);
    const tree = render(<ReportBody report={written} s={en} name="Pa" askingId={null} askedIds={new Set()} onAsk={() => {}} hasNextVisit locale="en-SG" />);
    const boundary = all(tree, byTestId("insights-boundary"))[0]!;
    expect(text([boundary])).toContain("Ask your doctor.");
  });

  it("'Ask this' files the insight's words through the visit-questions route; asking it again is disabled until it settles, and the kept line shows once it has", () => {
    const onAsk = vi.fn();
    const asking = render(<InsightRow insight={insight()} s={en} asking asked={false} onAsk={onAsk} />);
    const [askButton] = all(asking, byTestId("insight-ask"));
    expect(askButton!.props.disabled).toBe(true);

    const idle = render(<InsightRow insight={insight()} s={en} asking={false} asked={false} onAsk={onAsk} />);
    const [idleButton] = all(idle, byTestId("insight-ask"));
    expect(idleButton!.props.disabled).toBe(false);
    expect(text([idleButton!])).toContain("Ask Dr Tan this");
    (idleButton!.props.onClick as () => void)();
    expect(onAsk).toHaveBeenCalledWith(insight());

    const done = render(<InsightRow insight={insight()} s={en} asking={false} asked={true} onAsk={onAsk} />);
    expect(text(all(done, byTestId("insight-asked")))).toContain("Nura kept this question for your visit.");
  });

  it("with no visit booked, the row says so instead of offering an action with nowhere to file it", () => {
    const tree = render(<InsightRow insight={insight()} s={en} asking={false} asked={false} onAsk={undefined} />);
    expect(all(tree, byTestId("insight-ask"))).toHaveLength(0);
    expect(text(all(tree, byTestId("insight-no-visit")))).toContain("There is no visit booked yet to take this to.");
  });

  it("the Health card leads with the last time Nura looked and the headline of what it found", () => {
    const onOpen = vi.fn();
    const onGenerate = vi.fn();
    const written = report([{ key: "what_changed", title: "What changed", insights: [insight({ text: "Headline line." })] }]);
    const tree = render(<InsightsCard s={en} owner name="" report={written} checked locale="en-SG" onOpen={onOpen} onGenerate={onGenerate} />);
    expect(softText(all(tree, byTestId("insights-headline")))).toBe("Headline line.");
    (all(tree, byTestId("insights-open"))[0]!.props.onClick as () => void)();
    expect(onOpen).toHaveBeenCalled();
    (all(tree, byTestId("insights-generate"))[0]!.props.onClick as () => void)();
    expect(onGenerate).toHaveBeenCalled();
  });

  it("before anything has been generated, the card says so plainly instead of showing a blank space", () => {
    const tree = render(<InsightsCard s={en} owner name="" report={null} checked locale="en-SG" onOpen={() => {}} onGenerate={() => {}} />);
    expect(text(all(tree, byTestId("insights-none")))).toBe("Nura has not looked at your week yet.");
  });
});
