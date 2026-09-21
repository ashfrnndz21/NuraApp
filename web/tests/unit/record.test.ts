import { describe, expect, it } from "vitest";
import type { EpisodeViewOut, FeedItemOut, LineOut, ReviewCardOut, ReviewFieldOut, TimelineItemOut } from "../../src/api/types";
import {
  confidenceLine,
  countOf,
  dayInOrder,
  dayOf,
  groupPapersByYear,
  hangingLines,
  hubEntries,
  labelFromCard,
  lineForCard,
  lineQuestions,
  numberText,
  onePage,
  outcomeLine,
  paperStateChip,
  papersToPut,
  providerLines,
  pointRangeLine,
  rangeLine,
  rangeSourceLine,
  clockLine,
  reorderActions,
  severityLine,
  tidyLabel,
  trendLines,
  withReading,
  withTime,
  withWalk,
} from "../../src/record/model";
import { en } from "../../src/strings/en";

const ALL = ["medicines", "visits", "readings", "records", "notes", "money", "family", "emergency", "ask", "send"];

const line = (over: Partial<LineOut> = {}): LineOut => ({
  line_id: "line-1",
  name: "your blood pressure tablet",
  generic: "amlodipine",
  brand: "Norvasc",
  strength: "5 mg",
  form: "tablet",
  high_risk: false,
  dose: { amount: 1, unit: "tablet", frequency: "od", anchors: [] },
  prescriber: "Dr Tan",
  status: "active",
  started_at: "2026-09-14T00:00:00Z",
  count: {
    remaining: 5,
    unit: "tablet",
    dispensed: 5,
    taken: 0,
    daily_amount: 1,
    days_left: 5,
    reorder_date: "2026-09-16",
    reorder_due: true,
    lead_time_days: 3,
    basis: "taps",
    lines: ["You have 5 tablets of your blood pressure tablet left."],
    reorder: ["Your blood pressure tablet runs out on Saturday 19 September."],
    reorder_actions: { ask_to_order: "Ask the family to order.", i_have_more: "I have more at home." },
  },
  flags: [],
  doctor_question: [],
  taken_label: null,
  due_now: false,
  missed: false,
  source: "This comes from the label you kept on Monday 14 September.",
  fact_id: "fact-1",
  confidence: 1,
  confidence_state: "confirmed_by_person",
  duplicate_of: [],
  ...over,
});

const field = (attribute: string, value: unknown, over: Partial<ReviewFieldOut> = {}): ReviewFieldOut => ({
  field_id: attribute,
  position: 0,
  subject: "medicine",
  attribute,
  value,
  unit: null,
  confidence: 0.9,
  needs_confirm: false,
  unreadable: false,
  prompt: null,
  page: null,
  range: null,
  label_on_paper: null,
  state: "proposed",
  corrected_value: null,
  fact_id: null,
  ...over,
});

const card = (over: Partial<ReviewCardOut> = {}): ReviewCardOut => ({
  card_id: "card-1",
  profile_id: "p",
  artifact_id: "art-1",
  document_kind: "lab_report",
  document_date: null,
  asked_as: null,
  source: null,
  notice: null,
  high_risk_class: null,
  created_at: "2026-09-14T00:00:00Z",
  confirmed_at: "2026-09-14T00:10:00Z",
  fields: [],
  ...over,
});

const item = (artifacts: number, facts: number): TimelineItemOut => ({
  kind: "episode",
  id: "e",
  at: "2026-09-14T00:00:00Z",
  appointment: null,
  provider: null,
  episode: { episode_id: "e", kind: "illness", label: "chest infection", opened_at: "2026-09-10T00:00:00Z", closed_at: null },
  visits: [],
  artifacts: Array.from({ length: artifacts }, (_, n) => ({ artifact_id: `a${n}`, kind: "photo", content_type: "image/png", captured_at: "2026-09-14T00:00:00Z", source_channel: "app" })),
  events: [],
  facts: Array.from({ length: facts }, (_, n) => ({ fact_id: `f${n}`, subject: "blood_pressure", attribute: "reading", value: {}, unit: null, valid_from: "2026-09-14T00:00:00Z" })),
  notes: [],
});

describe("the Record's first screen", () => {
  it("opens on his medicines, his papers and his day in his density", () => {
    expect(hubEntries("patient", ALL).slice(0, 3)).toEqual(["medicines", "papers", "routine"]);
  });

  it("opens on what changed and the visits in hers, and offers only the parts a key opens", () => {
    expect(hubEntries("caregiver", ALL).slice(0, 2)).toEqual(["changes", "timeline"]);
    expect(hubEntries("caregiver", ["medicines"])).toEqual(["changes", "medicines", "routine"]);
  });

  it("shows one of a list a screen, never past its ends", () => {
    expect(onePage(["a", "b", "c"], 5)).toEqual({ item: "c", index: 2, total: 3 });
    expect(onePage([], 0)).toEqual({ item: null, index: 0, total: 0 });
  });
});

describe("his medicines", () => {
  it("says how sure Nura is of each line, in words", () => {
    expect(confidenceLine(line(), en)).toBe("You said yes to this.");
    expect(confidenceLine(line({ confidence_state: "extracted", confidence: 0.95 }), en)).toBe("Nura read this clearly.");
    expect(confidenceLine(line({ confidence_state: "extracted", confidence: 0.6 }), en)).toBe("Please check this one.");
    expect(confidenceLine(line({ confidence_state: "disputed" }), en)).toBe("Someone said this is not right.");
  });

  it("gives the reorder card's buttons in the backend's words, only at the threshold", () => {
    expect(reorderActions(line())).toEqual({ askToOrder: "Ask the family to order.", iHaveMore: "I have more at home." });
    expect(reorderActions(line({ count: { ...line().count!, reorder_due: false, reorder_actions: {} } }))).toBeNull();
  });

  it("finds the line a reorder card is about by the fact it cites", () => {
    const cardOnFeed = { why: { plain: "", kind: "reorder", fact_ids: ["fact-2"] } } as unknown as FeedItemOut;
    expect(lineForCard(cardOnFeed, [line(), line({ line_id: "line-2", fact_id: "fact-2" })])?.line_id).toBe("line-2");
    expect(lineForCard({ why: {} } as FeedItemOut, [line()])).toBeNull();
  });

  it("puts a line's own questions before its flags', once each", () => {
    const flagged = line({
      doctor_question: ["Ask Dr Tan about the new amount."],
      flags: [{ other_line_id: "x", other_generic: "aspirin", severity: "major", text_id: "t", question: ["Ask Dr Tan about the new amount.", "Ask Dr Tan if these two go together."] }],
    });
    expect(lineQuestions(flagged)).toEqual(["Ask Dr Tan about the new amount.", "Ask Dr Tan if these two go together."]);
  });

  it("reads a label photo's card into a label he checks, leaving what was not read empty", () => {
    const label = labelFromCard(
      card({
        document_kind: "medicine_label",
        fields: [
          field("name", "Warfarin"),
          field("strength", 3, { unit: "mg" }),
          field("dose", { drug: "Warfarin", instruction: "1 tablet once a day at night", as_printed: "1 biji sekali sehari waktu malam" }, { unit: "tablet" }),
          field("quantity", 28, { unit: "tablets" }),
          field("prescriber", null, { unreadable: true }),
        ],
      }),
    );
    expect(label).toEqual({ generic: "warfarin", strength: "3 mg", dose_text: "1 biji sekali sehari waktu malam", quantity: 28 });
  });

  it("asks nothing of the backend until there is a name and how to take it", () => {
    expect(tidyLabel({ generic: "Aspirin ", dose_text: "" })).toBeNull();
    expect(tidyLabel({ generic: " Aspirin", strength: "100 mg", dose_text: "1 tab OD", quantity: 30 })).toEqual({
      generic: "aspirin",
      strength: "100 mg",
      form: null,
      dose_text: "1 tab OD",
      quantity: 30,
      prescriber: null,
    });
  });

  it("takes a count of tablets found at home only as a whole number", () => {
    expect(countOf("20")).toBe(20);
    expect(countOf("0")).toBeNull();
    expect(countOf("2.5")).toBeNull();
    expect(countOf("twenty")).toBeNull();
  });

  it("says what a label means and how much an interaction matters in whole lines", () => {
    expect(outcomeLine("new_line", en)).toBe("This is a new medicine for your list.");
    expect(outcomeLine("duplicate", en)).toBe("Nura already has this.");
    expect(severityLine("major", en)).toBe("This one matters a lot.");
    expect(severityLine("unheard-of", en)).toBe("This one matters.");
  });
});

describe("the timeline, an illness, the directory", () => {
  it("says how much hangs off a visit or an illness", () => {
    expect(hangingLines(item(0, 0), en)).toEqual(["Nothing is with it yet."]);
    expect(hangingLines(item(1, 1), en)).toEqual(["One paper is with it.", "Nura wrote down one thing from it."]);
    expect(hangingLines(item(3, 8), en)).toEqual(["3 papers are with it.", "Nura wrote down 8 things from it."]);
  });

  it("offers the chief only confirmed papers not already with the illness", () => {
    const view = { episode: item(1, 0), visits: [], withheld: [] } as EpisodeViewOut;
    const cards = [card({ card_id: "c0", artifact_id: "a0" }), card({ card_id: "c1", artifact_id: "lab" }), card({ card_id: "c2", artifact_id: "open", confirmed_at: null })];
    expect(papersToPut(cards, view).map((each) => each.card_id)).toEqual(["c1"]);
  });

  it("counts a doctor's visits and names the last and the next", () => {
    const visit = { appointment_id: "v", provider_id: "p", scheduled_at: "2026-09-04T01:00:00Z", status: "attended", purpose: "check-up", episode_id: null };
    const summary = { provider: { provider_id: "p", name: "Dr Tan", kind: "doctor", region: "SG" as const, phone_e164: null, address: null, category: null }, visits: 2, last_visit: visit, next_visit: null };
    expect(providerLines(summary, () => "Friday 4 September", en)).toEqual(["Nura has 2 visits here.", "The last visit was on Friday 4 September."]);
  });
});

describe("a lab trend", () => {
  const range = { lower: null, upper: 200, unit: "mg/dL", source: "guideline", source_id: "ncep-atp3-2001", lab: null };

  it("places each result against its range, in whole lines, and says whose range it is", () => {
    // His density: no unit he does not use (plain words, rule 12).
    expect(rangeLine(range, en)).toBe("For most people this number is under 200.");
    expect(rangeLine({ ...range, lower: 1.0, upper: 1.5 }, en)).toBe("For most people this number is 1 to 1.5.");
    // Hers: the unit stays with the number.
    expect(rangeLine(range, en, true)).toBe("For most people this number is under 200 mg/dL.");
    expect(rangeLine({ ...range, lower: 1.0, upper: 1.5 }, en, true)).toBe("For most people this number is 1 to 1.5 mg/dL.");
    expect(rangeLine(null, en)).toBe("Nura has no usual number for this one.");
    expect(rangeSourceLine(range, en)).toBe("The usual number comes from a guide for your age.");
    expect(rangeSourceLine({ ...range, source: "lab", source_id: "lab:bukit_lab" }, en)).toBe("The usual number is printed on your blood test.");
    // The backend's `source` decides; nothing is read into the id.
    expect(rangeSourceLine({ ...range, source: "guideline", source_id: "lab:bukit_lab" }, en)).toBe("The usual number comes from a guide for your age.");
    expect(numberText(5.2)).toBe("5.2");
  });

  it("says a time of his day the way every time in the app is said (timeLine), never a bare code", () => {
    expect(clockLine("07:00", "en-SG")).toMatch(/^7:00\sam$/);
    expect(clockLine("19:30", "en-SG")).toMatch(/^7:30\spm$/);
    expect(clockLine("19:30", "ms-MY")).toBe("19:30");
    expect(clockLine("", "en-SG")).toBe("");
  });

  it("says why a result has no usual number beside it, when the backend says", () => {
    expect(pointRangeLine({ range: null, no_range_because: "needs_age" }, en)).toBe("Nura needs your age to find the usual number.");
    expect(pointRangeLine({ range: null, no_range_because: "needs_sex" }, en)).toBe("Nura needs to know if you are a man or a woman.");
    expect(pointRangeLine({ range: null, no_range_because: "none_on_file" }, en)).toBe("Nura has no usual number for this one.");
    expect(pointRangeLine({ range: null, no_range_because: "something_new" }, en)).toBe("Nura has no usual number for this one.");
    expect(pointRangeLine({ range: null, no_range_because: null }, en)).toBe("Nura has no usual number for this one.");
    expect(pointRangeLine({ range, no_range_because: null }, en)).toBe("For most people this number is under 200.");
  });

  it("keeps the boundary apart and last, whatever order it came in", () => {
    const said = trendLines({
      lines: ["Your cholesterol was 212 on Friday 29 August 2025.", "It has come down since Thursday 7 September 2023.", "Nura put your blood tests side by side.", "This is not a doctor's advice.", "Ask Dr Tan."],
      boundary: "Nura put your blood tests side by side.\nThis is not a doctor's advice.\nAsk Dr Tan.",
    });
    expect(said.body).toEqual(["Your cholesterol was 212 on Friday 29 August 2025.", "It has come down since Thursday 7 September 2023."]);
    expect(said.boundary.at(-1)).toBe("Ask Dr Tan.");
  });
});

describe("the day", () => {
  const routine = {
    anchors: { wake: "06:30", breakfast: "07:30", lunch: "12:30", dinner: "18:30", bed: "22:00" },
    reading_prompts: [["blood_pressure", "wake"]],
    walks: [],
    morning_card_at: "07:00",
  };

  it("starts her builder from the day as it is", () => {
    expect(dayOf(routine)).toEqual({ ...routine, reading_prompts: [["blood_pressure", "wake"]] });
  });

  it("keeps prompts and walks in the order of his day, so the yes and the write see one day", () => {
    let day = dayOf(routine);
    day = withReading(day, "weight", "bed", true);
    day = withReading(day, "blood_sugar", "wake", true);
    day = withWalk(withWalk(day, "dinner", true), "breakfast", true);
    expect(day.reading_prompts).toEqual([
      ["blood_pressure", "wake"],
      ["blood_sugar", "wake"],
      ["weight", "bed"],
    ]);
    expect(day.walks).toEqual(["breakfast", "dinner"]);
    expect(withReading(day, "weight", "bed", false).reading_prompts).toHaveLength(2);
  });

  it("asks for a yes only for times that rise through the day", () => {
    const day = dayOf(routine);
    expect(dayInOrder(day)).toBe(true);
    expect(dayInOrder(withTime(day, "lunch", "06:00"))).toBe(false);
    expect(dayInOrder(withTime(day, "bed", ""))).toBe(false);
  });
});

// --- "Your papers" (E02-07 library part B): the list's own state chip and year grouping -------

describe("paperStateChip: the list's own state chip per kind (library part B #2)", () => {
  it("is 'Check' (the question flag) while the card still waits for his yes", () => {
    const waiting = card({ confirmed_at: null });
    expect(paperStateChip(waiting, en)).toEqual({ label: "Check", state: "question" });
  });

  it("counts what is outside the paper's own printed range on a confirmed lab report", () => {
    const outside = card({
      document_kind: "lab_report",
      fields: [
        field("ldl", 4.0, { unit: "mmol/L", range: { text: "< 3.4", low: null, high: 3.4 } }),
        field("hdl", 1.2, { unit: "mmol/L", range: { text: "> 1.0", low: 1.0, high: null } }),
      ],
    });
    expect(paperStateChip(outside, en)).toEqual({ label: "1 outside", state: "attention" });
  });

  it("says 'All in range' when a confirmed lab report's own ranges are every one inside", () => {
    const inRange = card({
      document_kind: "lab_report",
      fields: [field("hdl", 1.2, { unit: "mmol/L", range: { text: "> 1.0", low: 1.0, high: null } })],
    });
    expect(paperStateChip(inRange, en)).toEqual({ label: "All in range", state: "ok" });
  });

  it("is the plain 'Read' for a confirmed kind that is not a lab report", () => {
    const letter = card({ document_kind: "discharge_letter", fields: [field("reason", "heart failure")] });
    expect(paperStateChip(letter, en)).toEqual({ label: "Read", state: null });
  });

  it("is 'Read' too for a confirmed lab report with nothing parsable on it", () => {
    const noRanges = card({ document_kind: "lab_report", fields: [field("note", "see attached")] });
    expect(paperStateChip(noRanges, en)).toEqual({ label: "Read", state: null });
  });
});

describe("groupPapersByYear: only once there are enough to need it (library part B #2)", () => {
  it("is empty — the caller renders the cards flat — at eight or fewer", () => {
    const cards = Array.from({ length: 8 }, (_, n) => card({ card_id: `c${n}`, created_at: "2026-09-14T00:00:00Z" }));
    expect(groupPapersByYear(cards)).toEqual([]);
  });

  it("groups by the paper's own printed date, falling back to when it came in, once there are more than eight", () => {
    const cards = [
      card({ card_id: "c0", document_date: "2026-01-05", created_at: "2026-01-05T00:00:00Z" }),
      card({ card_id: "c1", document_date: null, created_at: "2025-12-20T00:00:00Z" }),
      ...Array.from({ length: 7 }, (_, n) => card({ card_id: `c${n + 2}`, created_at: "2025-06-01T00:00:00Z" })),
    ];
    const groups = groupPapersByYear(cards);
    expect(groups.map((g) => g.year)).toEqual([2026, 2025]);
    expect(groups[0]!.cards.map((c) => c.card_id)).toEqual(["c0"]);
    // c1 has no printed date, so it falls back to when it came in (2025) and joins the rest.
    expect(groups[1]!.cards).toHaveLength(8);
    expect(groups[1]!.cards[0]!.card_id).toBe("c1");
  });
});
