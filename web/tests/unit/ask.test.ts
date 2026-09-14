import { describe, expect, it } from "vitest";
import type { AnswerOut } from "../../src/api/types";
import { answerView, askMode, sourceOf } from "../../src/feed/ask";

const answer = (extra: Partial<AnswerOut> = {}): AnswerOut => ({
  question_artifact_id: "q1",
  mode: "voice",
  language: "en",
  answered: true,
  lines: [{ text: "Your blood pressure on Monday 14 September was 138 over 84.", cites: [{ kind: "fact", id: "f1" }, { kind: "event", id: "e1" }] }],
  honest: [],
  boundary: ["Nura read this from your papers.", "This is not a doctor's advice.", "Ask your doctor."],
  spoken: ["Your blood pressure on Monday 14 September was 138 over 84.", "Nura read this from your papers.", "This is not a doctor's advice.", "Ask your doctor."],
  withheld: [],
  ...extra,
});

describe("ask", () => {
  it("is voice in the patient's density and text in the caregiver's", () => {
    expect(askMode("patient")).toBe("voice");
    expect(askMode("caregiver")).toBe("text");
  });

  it("names a cited line's source by what it rests on; a line that cites nothing has none", () => {
    expect(sourceOf([{ kind: "medication_line", id: "l" }, { kind: "fact", id: "f" }])).toBe("sourceMedicines");
    expect(sourceOf([{ kind: "appointment", id: "a" }, { kind: "provider", id: "p" }])).toBe("sourceVisits");
    expect(sourceOf([{ kind: "fact", id: "f" }, { kind: "artifact", id: "x" }])).toBe("sourcePapers");
    expect(sourceOf([])).toBeNull();
  });

  it("shows the backend's words only, in its order: cited lines, the honest lines, the boundary last", () => {
    const view = answerView(answer({ honest: ["Nura does not have that written down."] }));
    expect(view.lines).toEqual([{ text: "Your blood pressure on Monday 14 September was 138 over 84.", source: "sourcePapers", clip: null }]);
    expect(view.honest).toEqual(["Nura does not have that written down."]);
    expect(view.boundary.at(-1)).toBe("Ask your doctor.");
    expect(view.spoken.at(-1)).toBe("Ask your doctor.");
    expect(view.withheld).toBe(false);
    expect(answerView(answer({ withheld: ["notes"] })).withheld).toBe(true);
  });

  it("a line about a recorded visit carries its clip, and is from his visits", () => {
    const clip = { artifact_id: "rec-1", start_s: 19.8, end_s: 28.9, doctor: "Dr Tan" };
    const view = answerView(
      answer({
        lines: [
          {
            text: "Dr Tan talked about this on Monday 14 September.",
            cites: [
              { kind: "summary_item", id: "i1" },
              { kind: "appointment", id: "a1" },
              { kind: "artifact", id: "rec-1", start_s: 19.8, end_s: 28.9 },
            ],
            clip,
          },
        ],
      }),
    );
    expect(view.lines[0]).toEqual({ text: "Dr Tan talked about this on Monday 14 September.", source: "sourceVisits", clip });
  });

  it("a line saying the visit's card waits for his yes is from his visits, and plays nothing", () => {
    const view = answerView(
      answer({
        lines: [
          {
            text: "Your card from Dr Tan on Monday 14 September is waiting for your yes.",
            cites: [
              { kind: "visit_summary", id: "c1" },
              { kind: "appointment", id: "a1" },
            ],
            clip: null,
          },
        ],
      }),
    );
    expect(view.lines[0]).toEqual({ text: "Your card from Dr Tan on Monday 14 September is waiting for your yes.", source: "sourceVisits", clip: null });
  });
});
