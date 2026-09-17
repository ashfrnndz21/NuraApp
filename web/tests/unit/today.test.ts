import { describe, expect, it } from "vitest";
import type { FeedItemOut, LineOut, SlotOut } from "../../src/api/types";
import { en } from "../../src/strings/en";
import {
  boundaryOf,
  dateLine,
  dayKey,
  feedCards,
  feedLines,
  greeting,
  dayMonthLine,
  heroFurnitureAllowed,
  homeHero,
  homeHeroWords,
  lineTitle,
  medicinesCard,
  nowCard,
  questionLines,
  readingLead,
  stateLines,
  timeLine,
  todayList,
  tookLine,
  whyLine,
} from "../../src/today/model";

const SOURCE = "This comes from the label you kept on Tuesday 1 September.";

const slot = (line_id: string, anchor: string, flags: Partial<SlotOut> = {}): SlotOut => ({
  line_id,
  generic: line_id,
  anchor,
  card: `Take 1 tablet of ${line_id} at ${anchor}.`,
  taken: false,
  taken_label: "Taken",
  due_now: false,
  missed: false,
  if_forgotten: [],
  source: SOURCE,
  ...flags,
});

const count = (days_left: number | null, lines: string[] = []) => ({
  remaining: 28,
  unit: "tablet",
  dispensed: 30,
  taken: 2,
  daily_amount: 1,
  days_left,
  reorder_date: null,
  reorder_due: false,
  lead_time_days: 3,
  basis: "taps",
  lines,
  reorder: [],
});

const line = (line_id: string, name: string, extra: Partial<LineOut> = {}): LineOut => ({
  line_id,
  name,
  generic: line_id,
  brand: null,
  strength: "5 mg",
  form: "tablet",
  high_risk: false,
  dose: { amount: 1, unit: "tablet", frequency: "od", anchors: ["breakfast"] },
  prescriber: "Dr Tan",
  status: "active",
  started_at: "2026-09-01T00:00:00Z",
  count: null,
  flags: [],
  doctor_question: [],
  taken_label: "Taken",
  due_now: false,
  missed: false,
  source: SOURCE,
  ...extra,
});

const item = (supply: string, headline: string, extra: Partial<FeedItemOut> = {}): FeedItemOut => ({
  item_id: headline,
  type: supply,
  supply,
  status: "generated",
  rendered_from_state: "s1",
  language: "en",
  format: "card",
  headline,
  body: [`${headline}.`],
  voice: [`${headline}.`],
  why: { kind: "x", plain: `Why ${headline}.` },
  priority: 1,
  caps_class: "x",
  scope: "medicines",
  deliver_to: "patient",
  autoplay: false,
  source_id: null,
  cite: null,
  boundary: null,
  day: "2026-09-14",
  created_at: "2026-09-14T00:00:00Z",
  expires_at: "2026-09-15T00:00:00Z",
  ...extra,
});

const lines = [line("amlodipine", "your blood pressure tablet"), line("warfarin", "the blood thinner tablet")];

describe("the Now card", () => {
  it("is the dose the backend marks due now, never the earliest untapped one, under its source line", () => {
    const slots = [
      slot("amlodipine", "breakfast", { missed: true, if_forgotten: ["If you forgot, leave it."] }),
      slot("warfarin", "dinner", { due_now: true, source: "This comes from what was typed in on Monday 7 September." }),
    ];
    expect(nowCard(slots, lines, en)).toEqual({
      kind: "due",
      lineId: "warfarin",
      anchor: "dinner",
      title: "The blood thinner tablet",
      sentence: "Take 1 tablet of warfarin at dinner.",
      provenance: "This comes from what was typed in on Monday 7 September.",
    });
  });

  it("shows the story's missed-dose lines, and no Taken, for a dose whose window has passed", () => {
    const slots = [slot("amlodipine", "breakfast", { missed: true, if_forgotten: ["If you forgot, leave it.", "Never take 2 at once."] })];
    expect(nowCard(slots, lines, en)).toEqual({
      kind: "missed",
      title: "Your blood pressure tablet",
      lines: ["If you forgot, leave it.", "Never take 2 at once."],
      provenance: SOURCE,
    });
  });

  it("says all taken, or nothing right now, or no medicines", () => {
    expect(nowCard([slot("amlodipine", "breakfast", { taken: true })], lines, en)).toEqual({ kind: "allTaken" });
    expect(nowCard([slot("amlodipine", "bed")], lines, en)).toEqual({ kind: "nothingNow" });
    expect(nowCard([], lines, en)).toEqual({ kind: "none" });
  });

  it("never puts the chemical name alone in the title", () => {
    expect(lineTitle(undefined, en)).toBe("Your tablet");
    expect(lineTitle(line("furosemide", ""), en)).toBe("Your tablet");
    const card = nowCard([slot("furosemide", "breakfast", { due_now: true })], [], en);
    expect(card.kind === "due" && card.title).toBe("Your tablet");
  });

  it("is a plain list of the day's own sentences on a page the phone kept", () => {
    expect(todayList([slot("amlodipine", "breakfast", { taken: true }), slot("warfarin", "bed", { due_now: true })])).toEqual([
      "Take 1 tablet of amlodipine at breakfast.",
      "Take 1 tablet of warfarin at bed.",
    ]);
  });
});

describe("the feed's cards", () => {
  it("are the red flags first, then the first two now and today cards, in the backend's order", () => {
    const items = [item("flag", "A fall"), item("now", "Your tablets today"), item("today", "Running low"), item("today", "Your blood pressure today"), item("gate", "That is all")];
    const cards = feedCards(items);
    expect(cards.flags.map((each) => each.headline)).toEqual(["A fall"]);
    expect(cards.forYou.map((each) => each.headline)).toEqual(["Your tablets today", "Running low"]);
    expect(whyLine(cards.forYou[0]!)).toBe("Why Your tablets today.");
  });

  it("show a card's boundary from its own field, once, under its body", () => {
    const learning = item("today", "Your blood thinner and your food", {
      body: ["Green leafy food changes how well it works.", "Nura explains one thing in simple words.", "This is not a doctor's advice.", "Ask your doctor."],
      boundary: "Nura explains one thing in simple words.\nThis is not a doctor's advice.\nAsk your doctor.",
    });
    expect(feedLines(learning)).toEqual({
      lines: ["Green leafy food changes how well it works."],
      boundary: ["Nura explains one thing in simple words.", "This is not a doctor's advice.", "Ask your doctor."],
    });
    expect(feedLines(item("now", "Your tablets today"))).toEqual({ lines: ["Your tablets today."], boundary: [] });
    expect(boundaryOf("A.\n\nB.\n")).toEqual(["A.", "B."]);
  });

  it("leave out a card he said Not for me to, and are empty when the feed is", () => {
    expect(feedCards([item("today", "Reading", { status: "dismissed" }), item("today", "Low")]).forYou.map((each) => each.headline)).toEqual(["Low"]);
    expect(feedCards([])).toEqual({ flags: [], forYou: [] });
  });
});

describe("the State card", () => {
  const model = (posture: "stable" | "watch" | "act", stale: boolean | null = false, chief: string | null = null) => ({ posture, stale, chief });
  const here = { flagAbove: false, kept: false };

  it("says steady or watching, and leaves the boundary to the backend's own line", () => {
    expect(stateLines(model("stable"), en, here)).toEqual(["Your day is steady."]);
    expect(stateLines(model("watch"), en, here)).toEqual(["Nura is keeping an eye on one thing for you.", "It is not a worry today."]);
    for (const posture of ["stable", "watch", "act"] as const) {
      expect(stateLines(model(posture), en, here).join(" ")).not.toMatch(/doctor's advice|Ask /);
    }
  });

  it("says only that it is from earlier today when stale, or when the phone kept it", () => {
    expect(stateLines(model("stable", true), en, here)).toEqual(["This is from earlier today."]);
    expect(stateLines(model("watch"), en, { flagAbove: false, kept: true })).toEqual(["This is from earlier today."]);
  });

  it("never says a calm sentence over act: whom to call, or the flag card above", () => {
    expect(stateLines(model("act", false, "Ash"), en, here)).toEqual(["There is one thing to do today.", "Call Ash now."]);
    expect(stateLines(model("act"), en, here)).toEqual(["There is one thing to do today.", "Call your family now."]);
    expect(stateLines(model("act", false, "Ash"), en, { flagAbove: true, kept: false })).toEqual([
      "There is one thing to do today.",
      "It is the first card on this page.",
    ]);
    expect(stateLines(model("act", true, "Ash"), en, here)).toEqual(["There is one thing to do today.", "Call Ash now.", "This is from earlier today."]);
    for (const where of [here, { flagAbove: true, kept: true }]) {
      for (const stale of [true, false, null]) expect(stateLines(model("act", stale), en, where)).not.toContain(en.today.stateStable);
    }
  });
});

describe("the medicines card", () => {
  const flagged = [
    line("aspirin", "the aspirin", {
      count: count(20, ["You have 20 tablets of the aspirin left."]),
      doctor_question: ["Ask Dr Tan about the new amount."],
      flags: [{ other_line_id: "w", other_generic: "warfarin", severity: "major", text_id: "bleeding", question: ["Ask Dr Tan about taking the aspirin and the blood thinner tablet together.", "Together they can make you bleed more easily."] }],
      source: "From the aspirin label.",
    }),
    line("warfarin", "the blood thinner tablet", {
      count: count(4, ["You have 4 tablets of the blood thinner tablet left.", "That is about 4 days."]),
      flags: [{ other_line_id: "a", other_generic: "aspirin", severity: "major", text_id: "bleeding", question: ["Ask Dr Tan about taking the aspirin and the blood thinner tablet together.", "Together they can make you bleed more easily."] }],
      source: "From the warfarin label.",
    }),
  ];

  it("carries the tablets nearest to running out and every question for the doctor, once each", () => {
    expect(questionLines(flagged)).toEqual([
      "Ask Dr Tan about the new amount.",
      "Ask Dr Tan about taking the aspirin and the blood thinner tablet together.",
      "Together they can make you bleed more easily.",
    ]);
    expect(medicinesCard(flagged, true)).toEqual({
      lines: [
        "You have 4 tablets of the blood thinner tablet left.",
        "That is about 4 days.",
        "Ask Dr Tan about the new amount.",
        "Ask Dr Tan about taking the aspirin and the blood thinner tablet together.",
        "Together they can make you bleed more easily.",
      ],
      provenance: "From the warfarin label.",
    });
  });

  it("keeps the questions when the feed carries today's cards, and is not there with nothing to say", () => {
    expect(medicinesCard(flagged, false)).toEqual({ lines: questionLines(flagged), provenance: "From the aspirin label." });
    expect(medicinesCard(lines, true)).toBeNull();
    expect(medicinesCard([line("x", "x", { count: count(9, ["You have 9 left."]) })], false)).toBeNull();
  });
});

describe("the words around them", () => {
  it("greet by the hour and say what he did", () => {
    expect(greeting(8, "Pa", en)).toBe("Good morning, Pa.");
    expect(greeting(20, "Pa", en)).toBe("Good evening, Pa.");
    expect(tookLine(8, en)).toBe("You took it this morning.");
    expect(tookLine(22, en)).toBe("You took it tonight.");
    expect(readingLead(8, en)).toBe("Write down this morning's number.");
    expect(readingLead(20, en)).toBe("Write down tonight's number.");
  });

  it("say the day with no comma and the time with no abbreviation", () => {
    const at = new Date(2026, 8, 14, 20, 5);
    expect(dateLine(at, "en-SG")).toBe("Monday 14 September");
    expect(dateLine(at, "ms-MY")).toBe("Isnin 14 September");
    expect(dateLine(at, "zh-CN")).toBe("9月14日星期一");
    expect(timeLine(at, "en-SG")).toMatch(/^8:05\s?pm$/);
    expect(timeLine(at, "ms-MY")).toBe("20:05");
    expect(timeLine(at, "zh-CN")).toBe("20:05");
  });

  it("key a day in the phone's own time zone", () => {
    expect(dayKey(new Date(2026, 8, 14, 23, 59))).toBe("2026-09-14");
  });
});

describe("her Home's hero line", () => {
  const line = "Nothing needs you today.";
  it("is the backend's own line when the State is current and nothing is flagged", () => {
    expect(homeHeroWords({ stale: false, line }, { flagged: false, kept: false }, en)).toBe(line);
  });
  it("says the State is from earlier when it is behind, or when the page is the phone's kept copy", () => {
    expect(homeHeroWords({ stale: true, line }, { flagged: false, kept: false }, en)).toBe(en.today.staleState);
    expect(homeHeroWords({ stale: false, line }, { flagged: false, kept: true }, en)).toBe(en.today.staleState);
  });
  it("reassures nobody while a red-flag card is on the page: the flag goes first", () => {
    expect(homeHeroWords({ stale: false, line }, { flagged: true, kept: false }, en)).toBeNull();
    expect(homeHeroWords({ stale: true, line }, { flagged: true, kept: true }, en)).toBeNull();
  });
});

describe("her Home's hero", () => {
  const page = { stale: false, line: "Nothing needs you today.", word: "Steady" };
  it("shows the State's word, its line and its chips when the page is current and nothing is flagged", () => {
    expect(homeHero(page, { flagged: false, kept: false }, en)).toEqual({ word: "Steady", line: page.line, drivers: true });
  });
  it("shows nothing of the State over a red-flag card: no word, no line, no chips", () => {
    expect(homeHero(page, { flagged: true, kept: false }, en)).toEqual({ word: null, line: null, drivers: false });
    expect(homeHero(page, { flagged: true, kept: true }, en)).toEqual({ word: null, line: null, drivers: false });
  });
  it("on the phone's kept page says it is from earlier, and shows no chips", () => {
    expect(homeHero(page, { flagged: false, kept: true }, en)).toEqual({ word: "Steady", line: en.today.staleState, drivers: false });
  });
});

describe("safety check 5: the Hero's furniture and the daily check-in", () => {
  it("may draw when nothing is flagged", () => {
    expect(heroFurnitureAllowed({ flagged: false })).toBe(true);
  });
  it("may not draw while a red-flag card is on the page — a wave and a smiling illustration over a flag reassure exactly as a State word would", () => {
    expect(heroFurnitureAllowed({ flagged: true })).toBe(false);
  });
});

describe("the day and month under a weekday", () => {
  it("says the day and the month with no weekday, so the visit tile says Monday once", () => {
    expect(dayMonthLine(new Date(2026, 8, 14), "en-SG")).toBe("14 September");
    expect(dayMonthLine(new Date(2026, 8, 14), "en-SG")).not.toContain("Monday");
  });
});

describe("his large-text setting, from State", () => {
  it("is on when the vision fact says so, off when it says no or says nothing, and unknown to a key that does not read it", async () => {
    const { largeTextOf } = await import("../../src/today/model");
    const facts = (value: unknown) => ({ dimensions: { functional: { facts: { vision: { large_text: { value } } } } } });
    expect(largeTextOf(facts(true))).toBe(true);
    expect(largeTextOf(facts(false))).toBe(false);
    expect(largeTextOf({ dimensions: { functional: { facts: {} } } })).toBe(false);
    expect(largeTextOf({ dimensions: { functional: null } })).toBeNull();
    expect(largeTextOf(null)).toBeNull();
  });
});
