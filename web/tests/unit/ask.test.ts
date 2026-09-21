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

  it("a line about a paper still waiting for his own yes is its own source, never 'your papers'", () => {
    // Review defect #11: a `review_card` cite fell through to `sourcePapers`, which wrongly
    // reads as though the paper were already confirmed — a card still waiting gets its own
    // caption instead.
    expect(sourceOf([{ kind: "review_card", id: "r1" }])).toBe("sourceReviewCard");
    const view = answerView(
      answer({
        lines: [
          {
            text: "A blood test dated Thursday 10 September is waiting for you to check.",
            cites: [{ kind: "review_card", id: "r1" }],
          },
        ],
      }),
    );
    expect(view.lines[0]).toEqual({
      text: "A blood test dated Thursday 10 September is waiting for you to check.",
      source: "sourceReviewCard",
      clip: null,
    });
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

  it("carries a clarifying question through, never together with lines (W2)", () => {
    const view = answerView(
      answer({
        lines: [],
        clarify: {
          question: "Which test is this about?",
          options: [
            { label: "Your blood test of Saturday 12 September", value: "tok-1" },
            { label: "Your hospital letter of Thursday 20 August", value: "tok-2" },
          ],
          allow_other: false,
        },
      }),
    );
    expect(view.clarify).not.toBeNull();
    expect(view.clarify?.question).toBe("Which test is this about?");
    expect(view.clarify?.options).toHaveLength(2);
    expect(view.clarify?.options[0]?.value).toBe("tok-1");
  });

  it("is null when the answer carries no clarifying question — every ordinary answer, exactly as today", () => {
    const view = answerView(answer());
    expect(view.clarify).toBeNull();
  });

  it("a free-text clarify (a cost question) carries no options and allow_other", () => {
    const view = answerView(
      answer({ lines: [], clarify: { question: "What is this cost for?", options: [], allow_other: true } }),
    );
    expect(view.clarify?.options).toEqual([]);
    expect(view.clarify?.allow_other).toBe(true);
  });

  it("a line saying the visit's card waits for his yes is from his visits, and plays nothing", () => {
    const view = answerView(
      answer({
        lines: [
          {
            text: "What Dr Tan said on Monday 14 September is waiting for your yes.",
            cites: [
              { kind: "visit_summary", id: "c1" },
              { kind: "appointment", id: "a1" },
            ],
            clip: null,
          },
        ],
      }),
    );
    expect(view.lines[0]).toEqual({ text: "What Dr Tan said on Monday 14 September is waiting for your yes.", source: "sourceVisits", clip: null });
  });
});
