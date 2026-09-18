import { describe, expect, it } from "vitest";
import type { ReviewCardOut, ReviewFieldOut } from "../../src/api/types";
import { canCorrect, confidenceLine, decide, decisionsFor, fieldLabel, kindLine, parseNumber, pillProposalLine, readable, spokenLine, startingEdits, valueText } from "../../src/onboarding/review";
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
  unreadable: false,
  prompt: null,
  page: null,
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
  asked_as: null,
  source: null,
  notice: null,
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

describe("a line Nura could not read (E02-02)", () => {
  const freq: ReviewFieldOut = { ...field("f-freq", "frequency", null, true, 4), subject: "medicine", unreadable: true, prompt: ["Nura could not read how often.", "Please type it from the slip."] };

  it("starts with an empty box, and can be typed", () => {
    expect(startingEdits(card([freq]))["f-freq"]).toEqual({ text: "", leftOut: false });
    expect(canCorrect(freq)).toBe(true);
  });

  it("is never confirmed as read: an empty box waits, what he typed is the correction", () => {
    expect(decide(freq, { text: "", leftOut: false }).ok).toBe(false);
    expect(decide(freq, { text: " twice a day ", leftOut: false })).toEqual({
      ok: true,
      decision: { field_id: "f-freq", decision: "corrected", corrected_value: "twice a day" },
    });
    expect(decide(freq, { text: "2", leftOut: false })).toEqual({
      ok: true,
      decision: { field_id: "f-freq", decision: "corrected", corrected_value: 2 },
    });
    expect(decide(freq, { text: "", leftOut: true })).toEqual({ ok: true, decision: { field_id: "f-freq", decision: "rejected" } });
  });

  it("says so in words, and its spoken twin is the backend's own prompt", () => {
    expect(confidenceLine(freq, en)).toBe("Nura could not read this one.");
    expect(spokenLine(freq, en)).toEqual(["How often to take it", "Nura could not read how often.", "Please type it from the slip."]);
    expect(spokenLine({ ...freq, prompt: null }, en)).toEqual(["How often to take it", en.onboarding.records.typeIt]);
  });
});

describe("every line has its spoken twin", () => {
  it("says what the line is, what was read and how sure Nura is", () => {
    expect(spokenLine(tg, en)).toEqual(["The blood fats", "64 mg/dL", "Please check this one."]);
    expect(spokenLine({ ...name, subject: "medicine" }, en)).toEqual(["The medicine", "Warfarin", "Nura is sure of this one."]);
  });
});

describe("the kinds of paper since E02 capture", () => {
  it("names each kind, and treats a page that is not a health paper as nothing to say yes to", () => {
    expect(kindLine("discharge_letter", en)).toBe("This is a hospital letter.");
    expect(kindLine("handwritten_prescription", en)).toBe(en.onboarding.records.kindHandwritten);
    expect(kindLine("device_screen", en)).toBe(en.onboarding.records.kindDeviceScreen);
    expect(kindLine("insurance_letter", en)).toBe(en.onboarding.records.kindInsuranceLetter);
    expect(readable(card([tg], "not_health"))).toBe(false);
  });

  it("treats a kind of photo Nura never opened at all as nothing to say yes to, too", () => {
    expect(kindLine("unsupported_file_type", en)).toBe(en.onboarding.records.kindUnknown);
    expect(readable(card([], "unsupported_file_type"))).toBe(false);
    // Even if the backend ever sent fields alongside it, the card still has nothing to
    // confirm: this kind was never read, so there is nothing genuine to say yes to.
    expect(readable(card([tg], "unsupported_file_type"))).toBe(false);
  });
});

describe("a pill photo and a pharmacy receipt (#pill-receipt)", () => {
  const imprint = field("f-imprint", "imprint", "IP 190", false, 0);
  const pillName = { ...field("f-pill-name", "name", "paracetamol", true, 1), subject: "medicine" };
  const pillStrength = { ...field("f-pill-strength", "strength", "500 mg", true, 2), subject: "medicine" };
  const item1Name = { ...field("f-item1-name", "name", "Panadol", false, 0), subject: "item_1" };
  const item1Total = { ...field("f-item1-total", "total", 12.5, false, 1), subject: "item_1", unit: "SGD" };

  it("names the two new kinds, never by their code", () => {
    expect(kindLine("pill_photo", en)).toBe(en.onboarding.records.kindPillPhoto);
    expect(kindLine("pharmacy_receipt", en)).toBe(en.onboarding.records.kindPharmacyReceipt);
  });

  it("labels a pill's own fields, and every receipt line's fields the same way whichever item it is", () => {
    expect(fieldLabel({ subject: "pill", attribute: "imprint" }, en)).toBe(en.onboarding.fields.pill!.imprint);
    expect(fieldLabel({ subject: "pill", attribute: "score_line" }, en)).toBe(en.onboarding.fields.pill!.score_line);
    expect(fieldLabel({ subject: "receipt", attribute: "pharmacy" }, en)).toBe(en.onboarding.fields.receipt!.pharmacy);
    expect(fieldLabel({ subject: "item_1", attribute: "total" }, en)).toBe(en.onboarding.fields.item!.total);
    expect(fieldLabel({ subject: "item_12", attribute: "quantity" }, en)).toBe(en.onboarding.fields.item!.quantity);
  });

  it("proposes a pill's guess with the pharmacist line, only on a pill photo that guessed a medicine", () => {
    expect(pillProposalLine(card([imprint, pillName, pillStrength], "pill_photo"), en)).toBe(
      "This looks like paracetamol 500 mg — check with the pharmacist.",
    );
    // No medicine guess at all: no proposal line, the raw pill fields still stand alone.
    expect(pillProposalLine(card([imprint], "pill_photo"), en)).toBeNull();
    // Never on another kind, even if it happened to carry a "medicine" field.
    expect(pillProposalLine(card([pillName], "medicine_label"), en)).toBeNull();
  });

  it("keeps a receipt line's price fields readable, unit and all", () => {
    expect(spokenLine(item1Total, en)).toEqual([en.onboarding.fields.item!.total, "12.5 SGD", "Nura is sure of this one."]);
    expect(fieldLabel(item1Name, en)).toBe(en.onboarding.fields.item!.name);
  });
});
