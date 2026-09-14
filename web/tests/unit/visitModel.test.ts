import { describe, expect, it } from "vitest";
import type { LogisticsOut, VisitSummaryOut } from "../../src/api/types";
import { CONSENT_REFUSALS, logisticsView, summaryView, timer } from "../../src/visit/model";

const card = (driver: Partial<LogisticsOut["driver"]> = {}): LogisticsOut => ({
  appointment_id: "a1",
  provider_id: "p1",
  doctor: "Dr Tan",
  language: "en",
  scheduled_at: "2026-09-14T02:30:00Z",
  state_id: "s1",
  place: "Gleneagles Hospital, 6A Napier Road",
  note: { note_id: "n1", label: "Mei's note", text: "parking at B2", by_person_id: "m1", by_name: "Mei", written_at: "2026-09-13T00:00:00Z" },
  driver: { status: "suggested", person_id: "m1", name: "Mei", task_id: null, needs_yes: true, can_say_yes: true, ...driver },
  lines: [
    { section: "when", key: "visit_with", text: "You see Dr Tan on Monday 14 September at half past 10 in the morning.", spoken: "x" },
    { section: "note", key: "logistics_note_by", text: "Mei wrote a note about the place.", spoken: "y" },
  ],
  spoken: ["x", "y"],
  withheld: [],
});

describe("the logistics card", () => {
  it("is the backend's lines, the chief's note under her name, and a suggestion only this key may answer", () => {
    const view = logisticsView(card());
    expect(view.lines.map((line) => line.section)).toEqual(["when", "note"]);
    expect(view.note).toEqual({ label: "Mei's note", text: "parking at B2" });
    expect(view.suggestion).toEqual({ personId: "m1", name: "Mei" });
    expect(logisticsView(card({ can_say_yes: false })).suggestion).toBeNull();
    expect(logisticsView(card({ status: "assigned", needs_yes: false })).suggestion).toBeNull();
  });
});

const summary: VisitSummaryOut = {
  summary_id: "c1",
  appointment_id: "a1",
  artifact_id: "t1",
  language: "en",
  red_flag: false,
  state_id: "s1",
  lines: [
    "Dr Tan said this on Monday 14 September.",
    "Ask Dr Tan about the new amount of the water pill (frusemide).",
    "Every morning, stand on the scale before breakfast.",
    "Nura wrote this from what Dr Tan said.",
    "Ask Dr Tan.",
  ],
  spoken: [],
  boundary: "Nura wrote this from what Dr Tan said.\nAsk Dr Tan.",
  items: [
    { item_id: "i1", position: 0, kind: "medication_change", text: "Ask Dr Tan about the new amount of the water pill (frusemide).", payload: {}, confidence: 0.86, state: "proposed", clip_start_s: 19.8, clip_end_s: 28.9 },
    { item_id: "i2", position: 1, kind: "action", text: "Every morning, stand on the scale before breakfast.", payload: {}, confidence: 0.93, state: "proposed", clip_start_s: null, clip_end_s: null },
  ],
  created_at: "2026-09-14T02:00:00Z",
  recording_artifact_id: "rec-1",
};

describe("the post-visit card", () => {
  it("puts each line's clip under it, and the boundary last, apart", () => {
    const view = summaryView(summary);
    expect(view.lines).toEqual([
      { text: "Dr Tan said this on Monday 14 September.", clip: null },
      { text: "Ask Dr Tan about the new amount of the water pill (frusemide).", clip: { artifact_id: "rec-1", start_s: 19.8, end_s: 28.9 } },
      { text: "Every morning, stand on the scale before breakfast.", clip: null },
    ]);
    expect(view.boundary).toEqual(["Nura wrote this from what Dr Tan said.", "Ask Dr Tan."]);
  });

  it("has no clips when the notes were typed", () => {
    expect(summaryView({ ...summary, recording_artifact_id: null }).lines.every((line) => line.clip === null)).toBe(true);
  });
});

describe("the timer and the gate", () => {
  it("says minutes and seconds", () => {
    expect(timer(0)).toBe("0:00");
    expect(timer(66.4)).toBe("1:06");
    expect(timer(3599)).toBe("59:59");
  });

  it("knows which refusals mean the owner has not agreed to Nura listening", () => {
    expect(CONSENT_REFUSALS.has("ConsentWithheld")).toBe(true);
    expect(CONSENT_REFUSALS.has("OutOfScope")).toBe(false);
  });
});
