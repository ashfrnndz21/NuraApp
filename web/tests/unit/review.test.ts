import { describe, expect, it } from "vitest";
import type { ReviewCardOut, ReviewFieldOut } from "../../src/api/types";
import { canCorrect, confidenceLine, decide, decisionsFor, fieldLabel, kindLine, parseNumber, readable, startingEdits, valueText } from "../../src/onboarding/review";
import { en } from "../../src/strings/en";

const field = (field_id: string, attribute: string, value: unknown, needs_confirm = false, position = 0): ReviewFieldOut => ({
  field_id,
  position,
  subject: attribute === "dose" ? "medicine" : "lipid_panel",
  attribute,
  value,
  unit: typeof value === "number" ? "mg/dL" : null,
  confidence: needs_confirm ? 0.5 : 0.95,
  needs_confirm,
  state: "proposed",
  corrected_value: null,
  fact_id: null,
});

const card = (fields: ReviewFieldOut[], kind: ReviewCardOut["document_kind"] = "lab_report"): ReviewCardOut => ({
  card_id: "c1",
  profile_id: "p1",
  artifact_id: "a1",
  document_kind: kind,
  document_date: "2023-09-07",
  high_risk_class: null,
  created_at: "2026-09-14T08:00:00Z",
  confirmed_at: null,
  fields,
});

const tg = field("f-tg", "triglycerides", 64, true, 3);
const tc = field("f-tc", "total_cholesterol", 230, false, 0);
const dose = field("f-dose", "dose", { drug: "Warfarin", instruction: "1 tablet once a day at night", as_printed: "1 biji" }, true, 1);
const name = field("f-name", "name", "Warfarin", false, 2);

describe("what the box shows", () => {
  it("shows a number or words as the paper has them, and a dose by its instruction", () => {
    expect(valueText(64)).toBe("64");
    expect(valueText("Dr Lim")).toBe("Dr Lim");
    expect(valueText(dose.value)).toBe("1 tablet once a day at night");
    expect(valueText({ a: "x", b: 2, c: { d: 1 } })).toBe("x · 2");
  });

  it("lets a number or words be retyped, never a structured value", () => {
    expect(canCorrect(tg)).toBe(true);
    expect(canCorrect(name)).toBe(true);
    expect(canCorrect(dose)).toBe(false);
  });

  it("reads a number the way he might type it", () => {
    expect(parseNumber("54")).toBe(54);
    expect(parseNumber(" 5,4 ")).toBe(5.4);
    expect(parseNumber("fifty")).toBeNull();
    expect(parseNumber("54 mg")).toBeNull();
  });
});

describe("his decision on each line", () => {
  it("confirms a line he left as read", () => {
    expect(decide(tg, { text: "64", leftOut: false })).toEqual({ ok: true, decision: { field_id: "f-tg", decision: "confirmed" } });
  });

  it("corrects to exactly the number he typed, as a number", () => {
    expect(decide(tg, { text: "54", leftOut: false })).toEqual({
      ok: true,
      decision: { field_id: "f-tg", decision: "corrected", corrected_value: 54 },
    });
  });

  it("corrects words to the words he typed", () => {
    expect(decide(name, { text: " Warfarin Sodium ", leftOut: false })).toEqual({
      ok: true,
      decision: { field_id: "f-name", decision: "corrected", corrected_value: "Warfarin Sodium" },
    });
  });

  it("rejects a line he left out, whatever the box holds", () => {
    expect(decide(tg, { text: "anything", leftOut: true })).toEqual({ ok: true, decision: { field_id: "f-tg", decision: "rejected" } });
  });

  it("waits for him on an empty box or a word where a number was read", () => {
    expect(decide(tg, { text: "", leftOut: false }).ok).toBe(false);
    expect(decide(tg, { text: "fifty", leftOut: false }).ok).toBe(false);
  });

  it("never guesses a dose: a structured line is confirmed or left out, nothing else", () => {
    expect(decide(dose, { text: "2 tablets", leftOut: false })).toEqual({ ok: true, decision: { field_id: "f-dose", decision: "confirmed" } });
    expect(decide(dose, { text: "", leftOut: true })).toEqual({ ok: true, decision: { field_id: "f-dose", decision: "rejected" } });
  });

  it("sends one decision for every field, in the card's order, or names the ones still waiting", () => {
    const c = card([tg, dose, tc, name]);
    const edits = { ...startingEdits(c), "f-tg": { text: "54", leftOut: false }, "f-dose": { text: "", leftOut: true } };
    const { decisions, waiting } = decisionsFor(c, edits);
    expect(waiting).toEqual([]);
    expect(decisions.map((each) => [each.field_id, each.decision])).toEqual([
      ["f-tc", "confirmed"],
      ["f-dose", "rejected"],
      ["f-name", "confirmed"],
      ["f-tg", "corrected"],
    ]);
    expect(decisionsFor(c, { ...edits, "f-tg": { text: "x", leftOut: false } }).waiting).toEqual(["f-tg"]);
  });
});

describe("the words on the card", () => {
  it("names each line in his words, never by its code", () => {
    expect(fieldLabel(tg, en)).toBe("The blood fats");
    expect(fieldLabel({ subject: "medicine", attribute: "prescriber" }, en)).toBe("Which doctor wrote it");
    expect(fieldLabel({ subject: "x_ray", attribute: "finding" }, en)).toBe(en.onboarding.records.otherLine);
  });

  it("says how sure Nura is in words, from the backend's own threshold", () => {
    expect(confidenceLine(tg, en)).toBe("Please check this one.");
    expect(confidenceLine(tc, en)).toBe("Nura is sure of this one.");
  });

  it("says what kind of paper it is, and that an unreadable page has nothing to say yes to", () => {
    expect(kindLine("lab_report", en)).toBe("This is a blood test.");
    expect(kindLine("unknown", en)).toBe("Nura could not read this page.");
    expect(readable(card([tg]))).toBe(true);
    expect(readable(card([], "lab_report"))).toBe(false);
    expect(readable(card([tg], "unknown"))).toBe(false);
  });
});
