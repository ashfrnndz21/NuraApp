import { describe, expect, it } from "vitest";
import type { LineOut, SlotOut } from "../../src/api/types";
import { en } from "../../src/strings/en";
import { dayKey, greeting, nextDose, stateLines, supplyLines, tookLine } from "../../src/today/model";

const slot = (line_id: string, anchor: string, taken: boolean, card: string): SlotOut => ({
  line_id,
  generic: line_id,
  anchor,
  card,
  taken,
  taken_label: "Taken",
});

const line = (line_id: string, name: string, days_left: number | null, lines: string[] = []): LineOut => ({
  line_id,
  name,
  generic: line_id,
  brand: null,
  strength: "5 mg",
  form: "tablet",
  high_risk: false,
  dose: { amount: 1, unit: "tablet", frequency: "daily", anchors: ["breakfast"] },
  prescriber: "Dr Tan",
  status: "active",
  count: days_left === null ? null : { remaining: 28, unit: "tablet", dispensed: 30, taken: 2, daily_amount: 1, days_left, reorder_date: null, reorder_due: false, lead_time_days: 3, basis: "x", lines, reorder: [] },
  doctor_question: [],
  taken_label: "Taken",
});

describe("the Now card", () => {
  const lines = [line("amlodipine", "your blood pressure tablet", 28), line("warfarin", "the blood thinner tablet", 10)];

  it("is the first dose of the day not yet tapped, in his anchors' order", () => {
    const slots = [
      slot("warfarin", "bed", false, "Take 1 tablet of the blood thinner tablet before bed."),
      slot("amlodipine", "breakfast", false, "Take 1 tablet of your blood pressure tablet with breakfast."),
    ];
    const now = nextDose(slots, lines);
    expect(now.kind).toBe("dose");
    if (now.kind === "dose") {
      expect(now.title).toBe("Your blood pressure tablet");
      expect(now.sentence).toBe("Take 1 tablet of your blood pressure tablet with breakfast.");
      expect(now.anchor).toBe("breakfast");
      expect(now.left).toBe(2);
    }
  });

  it("moves to the next after Taken, then says every tablet is taken", () => {
    const after = nextDose([slot("amlodipine", "breakfast", true, "…"), slot("warfarin", "bed", false, "Bed.")], lines);
    expect(after.kind).toBe("dose");
    if (after.kind === "dose") expect(after.lineId).toBe("warfarin");
    expect(nextDose([slot("amlodipine", "breakfast", true, "…"), slot("warfarin", "bed", true, "…")], lines)).toEqual({ kind: "allTaken", count: 2 });
  });

  it("has nothing to show when there are no medicines", () => {
    expect(nextDose([], lines)).toEqual({ kind: "none" });
  });
});

describe("the other cards", () => {
  it("greet him by the time of day, as a whole line", () => {
    expect(greeting(7, "Pa", en)).toBe("Good morning, Pa.");
    expect(greeting(13, "Pa", en)).toBe("Good afternoon, Pa.");
    expect(greeting(20, "Pa", en)).toBe("Good evening, Pa.");
    expect(tookLine(8, en)).toBe("You took it this morning.");
    expect(tookLine(22, en)).toBe("You took it tonight.");
  });

  it("say the State in one line and the boundary in two, never an alarm", () => {
    expect(stateLines("stable", en)).toEqual([en.today.stateStable, en.today.boundary1, en.today.boundary2]);
    expect(stateLines("act", en)[0]).toBe(en.today.stateAct);
    for (const posture of ["stable", "watch", "act"] as const) {
      for (const text of stateLines(posture, en)) expect(text).not.toMatch(/urgent|alert|warning|!/i);
    }
  });

  it("pick the tablets nearest to running out, in the backend's own sentences", () => {
    const lines = [
      line("amlodipine", "your blood pressure tablet", 28, ["You have 28 tablets of your blood pressure tablet left."]),
      line("aspirin", "the aspirin", 4, ["You have 4 tablets of the aspirin left.", "That is about 4 days."]),
      line("nothing", "x", null),
    ];
    expect(supplyLines(lines)).toEqual(["You have 4 tablets of the aspirin left.", "That is about 4 days."]);
    expect(supplyLines([line("nothing", "x", null)])).toBeNull();
  });

  it("key a day in the phone's own time zone", () => {
    expect(dayKey(new Date(2026, 8, 14, 23, 59))).toBe("2026-09-14");
    expect(dayKey(new Date(2026, 0, 1, 0, 0))).toBe("2026-01-01");
  });
});
