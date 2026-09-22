import { describe, expect, it } from "vitest";
import type { ReviewCardOut, ReviewClarifyOut, ReviewFieldOut } from "../../src/api/types";
import { fieldValueDate } from "../../src/onboarding/dates";
import {
  canCorrect,
  confidenceLine,
  decide,
  decisionsFor,
  duplicateAddedOnLine,
  duplicateQuestionLead,
  effectiveValue,
  facilityField,
  fieldLabel,
  flagTone,
  flagWord,
  isResultRow,
  kindLine,
  kindTitle,
  parseNumber,
  pillProposalLine,
  rangeBarGeometry,
  rangeStatus,
  readable,
  readingChips,
  readingHeadline,
  readingTally,
  reportRow,
  saysItself,
  reportSections,
  sharedProvenance,
  spokenLine,
  startingEdits,
  valueText,
  readableValueText,
  whoseQuestionLead,
} from "../../src/onboarding/review";
import { en } from "../../src/strings/en";
import { ms } from "../../src/strings/ms";

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
  range: null,
  label_on_paper: null,
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
  clarify: null,
  discarded: false,
  duplicate_of_added_on: null,
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
    // A nested structure is read as far down as there is anything to read, never dropped
    // silently (E02 defect #2: "some lines showed NO value at all").
    expect(valueText({ a: "x", b: 2, c: { d: 1 } })).toBe("x · 2 · 1");
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

  it("renders every value shape the API can send, never blank (E02 defect #2)", () => {
    expect(valueText(true)).toBe("Yes");
    expect(valueText(false)).toBe("No");
    expect(valueText(["a", 2, "b"])).toBe("a · 2 · b");
    expect(valueText([{ a: "x" }, { b: 2 }])).toBe("x · 2");
    expect(valueText({ a: { b: "deep" } })).toBe("deep");
    expect(valueText(null)).toBe("");
    expect(valueText(undefined)).toBe("");
    expect(valueText({})).toBe("");
    expect(valueText([])).toBe("");
  });

  it("falls back to Nura's own words when nothing in the value is readable at all", () => {
    expect(readableValueText(64, en)).toBe("64");
    expect(readableValueText({}, en)).toBe(en.onboarding.records.valueUnreadable);
    expect(readableValueText(null, en)).toBe(en.onboarding.records.valueUnreadable);
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

  it("falls back to the paper's own words before the generic line name (E02 defect #1)", () => {
    // A canonical code Nura knows always wins, even with a label_on_paper alongside it.
    expect(fieldLabel({ ...tg, label_on_paper: "Trigs" }, en)).toBe("The blood fats");
    // No canonical code: the paper's own printed words, not "Another line on the paper".
    expect(fieldLabel({ subject: "lipid_panel", attribute: "other", label_on_paper: "Apo-B" }, en)).toBe("Apo-B");
    // A blank or missing label_on_paper still falls through to the generic line name.
    expect(fieldLabel({ subject: "lipid_panel", attribute: "other", label_on_paper: "  " }, en)).toBe(
      en.onboarding.records.otherLine,
    );
    expect(fieldLabel({ subject: "lipid_panel", attribute: "other" }, en)).toBe(en.onboarding.records.otherLine);
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

describe("where a number sits against the paper's own printed range (E02 defect #3)", () => {
  it("reads a two-sided range as inclusive at both ends", () => {
    const range = { low: 3.9, high: 6.0 };
    expect(rangeStatus(3.9, range)).toBe("in");
    expect(rangeStatus(6.0, range)).toBe("in");
    expect(rangeStatus(3.8, range)).toBe("below");
    expect(rangeStatus(6.1, range)).toBe("above");
  });

  it("says nothing about a backwards pair: no flag, no bar, not in the tally", () => {
    // #303 final check, NEW-3: a card stored before the reader refused low > high still carries
    // the numbers; 4.0 came out "below" 5.5–3.5 with a negative-width band.
    const backwards = { low: 5.5, high: 3.5 };
    expect(rangeStatus(4.0, backwards)).toBe("unknown");
    expect(rangeStatus(6.0, backwards)).toBe("unknown");
    expect(rangeBarGeometry(4.0, backwards)).toBeNull();
    expect(rangeStatus(4.0, { low: 4.0, high: 4.0 })).toBe("in"); // equal bounds are a range
  });

  it("reads an upper-only range as under, exclusive", () => {
    const range = { low: null, high: 150 };
    expect(rangeStatus(149, range)).toBe("in");
    expect(rangeStatus(150, range)).toBe("above");
    expect(rangeStatus(151, range)).toBe("above");
  });

  it("reads a lower-only range as or more, inclusive", () => {
    const range = { low: 40, high: null };
    expect(rangeStatus(40, range)).toBe("in");
    expect(rangeStatus(39, range)).toBe("below");
  });

  it("is unknown for anything that is not a plain number against a real range", () => {
    expect(rangeStatus("64", { low: 3.9, high: 6.0 })).toBe("unknown");
    // A value that still looks like a range as text ("<0.1") is never coerced to a number.
    expect(rangeStatus("<0.1", { low: null, high: 0.5 })).toBe("unknown");
    expect(rangeStatus(64, null)).toBe("unknown");
    expect(rangeStatus(64, undefined)).toBe("unknown");
    // An unparseable printed range ("Negative") keeps both bounds null: never a wrong bar.
    expect(rangeStatus(64, { low: null, high: null })).toBe("unknown");
  });

  it("is in exactly on a bound, for every shape of range", () => {
    expect(rangeStatus(3.9, { low: 3.9, high: 6.0 })).toBe("in"); // two-sided, low edge
    expect(rangeStatus(6.0, { low: 3.9, high: 6.0 })).toBe("in"); // two-sided, high edge
    expect(rangeStatus(40, { low: 40, high: null })).toBe("in"); // lower-only, inclusive
    expect(rangeStatus(150, { low: null, high: 150 })).toBe("above"); // upper-only, exclusive
  });
});

describe("the range bar's own geometry (the report table)", () => {
  it("draws nothing for a status that is unknown", () => {
    expect(rangeBarGeometry("64", { low: 3.9, high: 6.0 })).toBeNull();
    expect(rangeBarGeometry(64, null)).toBeNull();
    expect(rangeBarGeometry(64, { low: null, high: null })).toBeNull();
  });

  it("keeps the band and the marker inside the bar, whichever side the reading falls", () => {
    const range = { low: 3.9, high: 6.0 };
    for (const value of [2, 3.9, 5, 6.0, 8]) {
      const g = rangeBarGeometry(value, range)!;
      expect(g.bandStart).toBeGreaterThanOrEqual(0);
      expect(g.bandStart + g.bandWidth).toBeLessThanOrEqual(100);
      expect(g.markerAt).toBeGreaterThanOrEqual(0);
      expect(g.markerAt).toBeLessThanOrEqual(100);
    }
    // A reading further past the band sits further along the bar (monotonic, never clipped
    // silently to the same spot).
    const near = rangeBarGeometry(6.1, range)!;
    const far = rangeBarGeometry(9, range)!;
    expect(far.markerAt).toBeGreaterThan(near.markerAt);
  });

  it("opens a one-sided band toward the edge the paper never bounded", () => {
    const below = rangeBarGeometry(6.1, { low: null, high: 5.2 })!;
    expect(below.bandStart).toBe(0); // "below 5.2": in-range from the bar's own open edge
    const orMore = rangeBarGeometry(1.1, { low: 1.0, high: null })!;
    expect(orMore.bandStart + orMore.bandWidth).toBe(100); // "1.0 or more": open to the far edge
  });
});

describe("the flag and its tone", () => {
  it("is sage inside the paper's own range, amber outside, neither when unknown", () => {
    expect(flagTone("in")).toBe("ok");
    expect(flagTone("above")).toBe("attention");
    expect(flagTone("below")).toBe("attention");
    expect(flagTone("unknown")).toBeNull();
  });

  it("says the backend's own word, never a judgement invented here", () => {
    expect(flagWord("above", en)).toBe("Above");
    expect(flagWord("below", en)).toBe("Below");
    expect(flagWord("in", en)).toBe("In range");
    expect(flagWord("unknown", en)).toBeNull();
  });
});

describe("the reading screen's headline, chosen from the card he really read", () => {
  const ranged = (id: string, value: number, low: number | null, high: number | null, needs = false) => ({
    ...field(id, "x", value, needs),
    range: { low, high, text: "" },
  });

  it("counts what is outside the paper's own range, out of what is parsable", () => {
    const c = card([ranged("a", 6.1, null, 5.2), ranged("b", 1.1, 1.0, null), ranged("c", 64, null, null)]);
    expect(readingTally(c)).toEqual({ outside: 1, inRange: 1, parsable: 2, totalFields: 3, check: 0 });
    expect(readingHeadline(c, en)).toBe("1 of 2 are outside the range on the *paper.*");
  });

  it("says every one is inside rather than \"0 of {m}\"", () => {
    const c = card([ranged("a", 1.1, 1.0, null), ranged("b", 5.0, null, 5.2)]);
    expect(readingHeadline(c, en)).toBe("All 2 are inside the range on the *paper.*");
  });

  it("falls back to a plain count of lines when nothing on the card is parsable", () => {
    expect(readingHeadline(card([tg, tc, name]), en)).toBe("Nura read 3 lines from your *paper.*");
    expect(readingHeadline(card([], "medicine_label"), en)).toBe("Nura read 0 lines from your *paper.*");
  });

  it("assembles only the chips that have something in them", () => {
    const c = card([ranged("a", 6.1, null, 5.2), ranged("b", 1.1, 1.0, null, true)]);
    expect(readingChips(c, en)).toEqual([
      { key: "outside", label: "Outside range 1" },
      { key: "inRange", label: "In range 1" },
      { key: "check", label: "Check 1" },
    ]);
    expect(readingChips(card([tc]), en)).toEqual([]);
  });

  it("streams the same words in another language", () => {
    const c = card([ranged("a", 6.1, null, 5.2)]);
    expect(readingHeadline(c, ms)).toContain("julat");
  });
});

describe("one row of the report table, computed once", () => {
  it("is never blank: a row with nothing readable still has Nura's own words", () => {
    const blank = field("f-blank", "other", {}, false);
    const row = reportRow(blank, en);
    expect(row.valueText.length).toBeGreaterThan(0);
  });

  it("draws a bar and a flag only when the range is parsable, the range text either way", () => {
    const withRange = { ...tg, range: { low: null, high: 1.7, text: "below 1.7" } };
    const row = reportRow(withRange, en);
    expect(row.geometry).not.toBeNull();
    expect(row.flagWord).toBe("Above"); // 64 against "below 1.7"
    expect(row.rangeText).toBe("below 1.7");

    const unparsable = { ...tg, range: { low: null, high: null, text: "Negative" } };
    const row2 = reportRow(unparsable, en);
    expect(row2.geometry).toBeNull();
    expect(row2.flagWord).toBeNull();
    expect(row2.rangeText).toBe("Negative");
  });

  it("asks for him — needsAttention — only on needs_confirm or unreadable, never a sure row", () => {
    expect(reportRow(tc, en).needsAttention).toBe(false); // sure
    expect(reportRow(tg, en).needsAttention).toBe(true); // needs_confirm
    const unreadable: ReviewFieldOut = { ...field("f-u", "x", null, true), unreadable: true };
    expect(reportRow(unreadable, en).needsAttention).toBe(true);
  });

  it("shows the paper's own printed label only when it says more than his plain word", () => {
    expect(reportRow({ ...tg, label_on_paper: "Trigs" }, en).printedLabel).toBe("Trigs");
    expect(reportRow({ ...tg, label_on_paper: "The blood fats" }, en).printedLabel).toBeNull();
    expect(reportRow(tg, en).printedLabel).toBeNull();
  });
});

describe("the once-only provenance line under the table", () => {
  it("names the page when every field came from the same one", () => {
    const c = card([{ ...tg, page: 2 }, { ...tc, page: 2 }]);
    expect(sharedProvenance(c, "14 September 2026", en)).toBe("Nura read this from page 2, added on 14 September 2026.");
  });

  it("drops the page when the paper had none (a single photo)", () => {
    const c = card([tg, tc]);
    expect(sharedProvenance(c, "14 September 2026", en)).toBe("Nura read this from the paper you added on 14 September 2026.");
  });

  it("says nothing at all when the fields came from different pages — the caller falls back to a per-row line", () => {
    const c = card([{ ...tg, page: 1 }, { ...tc, page: 2 }]);
    expect(sharedProvenance(c, "14 September 2026", en)).toBeNull();
  });
});

describe("the report table's own short title and header facility (checkpoint 2)", () => {
  it("names the kind, not the sentence kindLine reads out loud", () => {
    expect(kindTitle("lab_report", en)).toBe("Blood test");
    expect(kindTitle("medicine_label", en)).toBe("Medicine label");
    expect(kindTitle("lab_report", en)).not.toBe(kindLine("lab_report", en));
  });

  it("finds the lab_report.facility (or .lab) field to show in the header, once, never as an ordinary row", () => {
    const facility = { ...field("f-fac", "facility", "Sunrise Medical Laboratory", false), subject: "lab_report" };
    expect(facilityField(card([tg, facility]))?.field_id).toBe("f-fac");
    expect(facilityField(card([tg, tc]))).toBeNull();
    const lab = { ...field("f-lab", "lab", "Bukit Lab", false), subject: "lab_report" };
    expect(facilityField(card([lab]))?.field_id).toBe("f-lab");
  });
});

// --- E02-07 library part A: the polished report table -----------------------------------------

describe("fieldValueDate: a field's own printed date, read as one (library part A #3)", () => {
  it("reads a bare date in his language, no weekday, no time", () => {
    expect(fieldValueDate("2025-01-21", "en-SG")).toBe("21 January 2025");
  });

  it("reads a date and time together — the owner's own screenshot, 'Collected On 2025-01-21T21:16'", () => {
    expect(fieldValueDate("2025-01-21T21:16", "en-SG")).toBe("21 January 2025, 9:16 pm");
  });

  it("reads a date with seconds and a timezone offset too", () => {
    expect(fieldValueDate("2026-08-20T08:00:00+08:00", "en-SG")).toBe("20 August 2026, 8:00 am");
  });

  it("is null for anything that is not a valid ISO date — left exactly as printed", () => {
    expect(fieldValueDate("heart failure", "en-SG")).toBeNull();
    expect(fieldValueDate("Dr Tan", "en-SG")).toBeNull();
    expect(fieldValueDate("2025-02-30", "en-SG")).toBeNull(); // no such calendar day
    expect(fieldValueDate("", "en-SG")).toBeNull();
  });
});

describe("reportRow: a date value reads as a date, other values are untouched (library part A #3)", () => {
  it("formats a field whose value is an ISO date", () => {
    const admitted = field("f-admit", "admitted_on", "2026-08-16");
    expect(reportRow(admitted, en, "en-SG").valueText).toBe("16 August 2026");
  });

  it("leaves a plain word value exactly as printed", () => {
    const reason = field("f-reason", "reason", "heart failure");
    expect(reportRow(reason, en, "en-SG").valueText).toBe("heart failure");
  });

  it("prefers the locale it is given, in Malay", () => {
    const admitted = field("f-admit", "admitted_on", "2026-08-16");
    expect(reportRow(admitted, en, "ms-MY").valueText).toContain("Ogos");
  });
});

describe("isResultRow: a measured result vs an administrative line (library part A #4)", () => {
  it("is a result when the row has a unit", () => {
    expect(isResultRow(reportRow(tg, en))).toBe(true);
  });

  it("is a result when the row has a printed range but no unit", () => {
    const withRange = field("f-r", "ldl", 4.0, false);
    const row = reportRow({ ...withRange, unit: null, range: { text: "< 3.4", low: null, high: 3.4 } }, en);
    expect(isResultRow(row)).toBe(true);
  });

  it("is never a result for a plain administrative line", () => {
    const doctor = field("f-doc", "doctor", "Dr Tan");
    expect(isResultRow(reportRow(doctor, en))).toBe(false);
  });
});

describe("reportSections: results first, needs-him never hidden (library part A #4)", () => {
  it("puts every result row, and any administrative row that needs him, in the open section", () => {
    const result = tg; // has a unit
    const doctor = field("f-doc", "doctor", "Dr Tan", true); // needs_confirm, no unit
    const reason = field("f-reason", "reason", "heart failure", false); // administrative, sure
    const { open, collapsed } = reportSections([reason, result, doctor], en);
    expect(open.map((f) => f.field_id)).toEqual([result.field_id, doctor.field_id]);
    expect(collapsed.map((f) => f.field_id)).toEqual([reason.field_id]);
  });

  it("collapses nothing when every row is a result or needs him", () => {
    const doctor = field("f-doc", "doctor", "Dr Tan", true);
    const { open, collapsed } = reportSections([tg, doctor], en);
    expect(open).toHaveLength(2);
    expect(collapsed).toHaveLength(0);
  });

  it("an unreadable administrative row is never hidden either", () => {
    const blurry = { ...field("f-b", "reason", null, false), unreadable: true };
    const { open, collapsed } = reportSections([blurry], en);
    expect(open.map((f) => f.field_id)).toEqual([blurry.field_id]);
    expect(collapsed).toHaveLength(0);
  });
  it("a letter is never folded: its words are the paper, whatever rows it has", () => {
    const reason = field("f-reason", "reason", "heart failure", false);
    const { open, collapsed } = reportSections([reason, tg], en, "en-SG", "discharge_letter");
    expect(open.map((f) => f.field_id)).toEqual([reason.field_id, tg.field_id]);
    expect(collapsed).toEqual([]);
  });
});

describe("effectiveValue: a confirmed card's own true value (library part B #3)", () => {
  it("is the read value while a field is only proposed", () => {
    expect(effectiveValue(tg)).toBe(tg.value);
  });

  it("is the corrected value once the field is corrected", () => {
    const corrected = { ...tg, state: "corrected" as const, corrected_value: 999 };
    expect(effectiveValue(corrected)).toBe(999);
  });

  it("falls back to the read value if corrected but nothing was kept", () => {
    const odd = { ...tg, state: "corrected" as const, corrected_value: null };
    expect(effectiveValue(odd)).toBe(tg.value);
  });
});

describe("a value that already opens with the paper's own label (22 Sep 2026, the owner's schedule)", () => {
  it("does not print the label again above it", () => {
    expect(saysItself("Overall Annual Limit: RM150,000 (Plan 1) / RM200,000 (Plan 2)", "Overall Annual Limit")).toBe(true);
    expect(saysItself("overall lifetime limit: No Limit", "Overall Lifetime Limit ")).toBe(true);
  });
  it("keeps the label when the value says something else, or nothing more than the label", () => {
    expect(saysItself("RM360", "Hospital Room & Board Charges")).toBe(false);
    expect(saysItself("Overall Annual Limit", "Overall Annual Limit")).toBe(false);
    expect(saysItself("", "Overall Annual Limit")).toBe(false);
  });
});

describe("whoseQuestionLead: which fields disagreed, never what the paper printed there (FIX BEFORE MERGE, the independent safety review)", () => {
  const mismatch = (mismatched: ReviewClarifyOut["mismatched"]): ReviewClarifyOut => ({
    kind: "whose_paper",
    mismatched,
    existing_card_id: null,
    existing_added_on: null,
  });

  it("names one field, in his own voice", () => {
    expect(whoseQuestionLead(mismatch(["birth_year"]), en, "")).toBe(
      "The year of birth on this paper is not yours.",
    );
  });

  it("joins two fields with 'and', and picks 'are' for more than one", () => {
    expect(whoseQuestionLead(mismatch(["name", "birth_year"]), en, "")).toBe(
      "The name and the year of birth on this paper are not yours.",
    );
  });

  it("speaks the caregiver's voice by his own name, never 'you'", () => {
    expect(whoseQuestionLead(mismatch(["name"]), en, "Pa")).toBe(
      "The name on this paper is not Pa's.",
    );
  });

  it("never renders any value the paper itself printed — only field names, whatever the card carries", () => {
    const withExtraneousFields = {
      ...mismatch(["name"]),
      // A malformed or old-shaped payload might still carry raw text; the type no longer
      // declares these fields at all, but the function must still never reach for them by
      // any other name.
    } as ReviewClarifyOut & { paper_name?: string };
    const lead = whoseQuestionLead(withExtraneousFields, en, "");
    expect(lead).not.toContain("Demo Patient Name");
    expect(lead).toBe("The name on this paper is not yours.");
  });

  it("falls back to the generic line when nothing is named as mismatched", () => {
    expect(whoseQuestionLead(mismatch([]), en, "")).toBe("This paper's details do not match your own.");
    expect(whoseQuestionLead(mismatch([]), en, "Pa")).toBe("This paper's details do not match Pa's own.");
  });

  it("says the same thing in Malay, field names and all", () => {
    expect(whoseQuestionLead(mismatch(["sex"]), ms, "")).toBe("Jantina pesakit pada surat ini bukan milik anda.");
  });
});

describe("duplicateQuestionLead / duplicateAddedOnLine: the caregiver twin (FIX BEFORE MERGE, the independent safety review)", () => {
  const clarify: ReviewClarifyOut = {
    kind: "duplicate_paper",
    mismatched: [],
    existing_card_id: "existing-1",
    existing_added_on: "2026-09-14",
  };

  it("reads 'you' in the patient's own voice", () => {
    expect(duplicateQuestionLead(clarify, en, "en-SG")).toContain("you added");
    expect(duplicateAddedOnLine("2026-09-14", en, "en-SG")).toBe("You added this paper on Monday 14 September.");
  });

  it("reads his own name in the caregiver's voice, never 'you'", () => {
    const lead = duplicateQuestionLead(clarify, en, "en-SG", "Pa");
    expect(lead).toContain("Pa added");
    expect(lead).not.toContain("you added");
    expect(duplicateAddedOnLine("2026-09-14", en, "en-SG", "Pa")).toBe("Pa added this paper on Monday 14 September.");
  });
});
