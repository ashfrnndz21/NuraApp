import { describe, expect, it } from "vitest";
import type { AppointmentOut, CountOut, FeedItemOut, LineOut, StateDriverOut } from "../../src/api/types";
import { statusLine } from "../../src/feed/model";
import { cadenceWord, isHisWatch } from "../../src/screens/ChiefPanels";
import { NextVisitAndReorder } from "../../src/screens/Today";
import { stringsFor } from "../../src/strings";
import { Chip, ChipRow, toneOf } from "../../src/ui/kit";
import { all, byTestId, hasClass, one, render, text } from "./ui/render";

/** Her Home (docs/design/full-experience.html, the Mei persona): the State's drivers as chips,
 *  the next-visit-and-reorder row of two, what Nura is watching for him, and what was sent to
 *  him this week — each read here with mocked data, the way `connectRender.test.tsx` and
 *  `insightsRender.test.tsx` read their own screens' presentational pieces. */

const en = stringsFor("en");

function count(overrides: Partial<CountOut> = {}): CountOut {
  return { remaining: 3, unit: "tablet", dispensed: 30, taken: 27, daily_amount: 1, days_left: 3, reorder_date: null, reorder_due: true, lead_time_days: 3, basis: "count", lines: ["Sugar tablets left. Order today."], reorder: [], ...overrides };
}

function line(overrides: Partial<LineOut> = {}): LineOut {
  return {
    line_id: "l1",
    name: "Metformin",
    generic: "metformin",
    brand: null,
    strength: "500 mg",
    form: "tablet",
    high_risk: false,
    dose: { amount: 1, unit: "tablet", frequency: "daily", anchors: ["dinner"] },
    prescriber: "Dr Tan",
    status: "active",
    started_at: "2026-02-01T00:00:00Z",
    count: count(),
    flags: [],
    doctor_question: [],
    taken_label: null,
    due_now: false,
    missed: false,
    ...overrides,
  } as unknown as LineOut;
}

function visit(overrides: Partial<AppointmentOut> = {}): AppointmentOut {
  return { appointment_id: "a1", provider_id: "p1", scheduled_at: "2026-09-24T10:00:00Z", status: "scheduled", purpose: "", doctor: "Dr Tan", ...overrides };
}

describe("her Home: the State's drivers as chips (docs/design/full-experience.html, Mei's tint card)", () => {
  it("draws the backend's driver text with a tone dot when it has one, none when it does not", () => {
    const drivers: StateDriverOut[] = [
      { key: "bp", text: "148 this morning", tone: "watch" },
      { key: "med", text: "Pressure tablet unchanged", tone: "good" },
      { key: "diet", text: "Salty lunches, 3", tone: null },
    ];
    const row = one(
      <ChipRow testId="drivers" label="Pa's most likely state">
        {drivers.map((driver) => (
          <Chip key={driver.key} tone={toneOf(driver.tone)}>
            {driver.text}
          </Chip>
        ))}
      </ChipRow>,
    );
    const chips = all(row, hasClass("glass-chip"));
    expect(chips.map((chip) => text(chip))).toEqual(["148 this morning", "Pressure tablet unchanged", "Salty lunches, 3"]);
    expect(chips.map((chip) => chip.props["data-tone"])).toEqual(["watch", "good", undefined]);
    // A tone dot only where there is a tone to show (Dot.tsx).
    expect(all(chips[0]!, hasClass("tone-dot"))).toHaveLength(1);
    expect(all(chips[2]!, hasClass("tone-dot"))).toHaveLength(0);
  });

  it("never turns an unrecognised tone into a coloured dot (Dot.tsx's closed set)", () => {
    expect(toneOf("rising")).toBeNull();
    expect(toneOf(undefined)).toBeNull();
    expect(toneOf("act")).toBe("act");
  });
});

describe("her Home: next visit and what to buy, side by side (docs/design/full-experience.html's row of two)", () => {
  it("draws both tiles in the two-up row when there is a visit and something to buy", () => {
    const tree = one(<NextVisitAndReorder visit={visit()} lines={[line()]} />);
    expect(tree.props.class).toBe("two-up");
    expect(all(tree, byTestId("next-visit-tile"))).toHaveLength(1);
    expect(all(tree, byTestId("supply-tile"))).toHaveLength(1);
    expect(text(all(tree, byTestId("supply-tile")))).toContain("Sugar tablets left. Order today.");
  });

  it("draws the visit alone, not paired, when nothing is near running out", () => {
    const tree = one(<NextVisitAndReorder visit={visit()} lines={[line({ count: null })]} />);
    expect(tree.props.class).toBeUndefined();
    expect(all(tree, byTestId("next-visit-tile"))).toHaveLength(1);
    expect(all(tree, byTestId("supply-tile"))).toHaveLength(0);
  });

  it("draws what to buy alone when no visit is booked", () => {
    const tree = one(<NextVisitAndReorder visit={null} lines={[line()]} />);
    expect(tree.props.class).toBeUndefined();
    expect(all(tree, byTestId("next-visit-tile"))).toHaveLength(0);
    expect(all(tree, byTestId("supply-tile"))).toHaveLength(1);
  });

  it("draws nothing at all rather than an empty row", () => {
    expect(render(<NextVisitAndReorder visit={null} lines={[line({ count: null })]} />)).toEqual([]);
  });
});

describe("her Home: what Nura is watching for him (docs/design/full-experience.html, 'Watching for Pa')", () => {
  it("says how often in the caregiver's plain word for every cadence the backend sends", () => {
    expect(cadenceWord("daily", en)).toBe(en.chief.daily);
    expect(cadenceWord("weekly", en)).toBe(en.chief.weekly);
    expect(cadenceWord("on_change", en)).toBe(en.chief.onChange);
    expect(cadenceWord("before_visits", en)).toBe(en.chief.beforeVisits);
    expect(cadenceWord("once", en)).toBe(en.chief.once);
  });

  it("falls back to the backend's own word for a cadence Nura has not named yet, rather than hiding it", () => {
    expect(cadenceWord("hourly", en)).toBe("hourly");
  });

  it("marks the fasting-month watch as his alone to pause or resume, and no other watch", () => {
    expect(isHisWatch({ kind: "seasonal", terms: ["fasting month"] })).toBe(true);
    expect(isHisWatch({ kind: "seasonal", terms: ["festive food"] })).toBe(false);
    expect(isHisWatch({ kind: "local", terms: ["fasting month"] })).toBe(false);
  });
});

describe("her Home: what was sent to him this week (docs/design/full-experience.html, 'Sent to Pa this week')", () => {
  function item(status: string, type = "explainer"): Pick<FeedItemOut, "status" | "type"> {
    return { status, type } as Pick<FeedItemOut, "status" | "type">;
  }

  it("names what became of each card sent to him — sent, opened, played, held, dismissed", () => {
    expect(statusLine(item("sent"), "caregiver")).toBe("statusSent");
    expect(statusLine(item("opened"), "caregiver")).toBe("statusOpened");
    expect(statusLine(item("played"), "caregiver")).toBe("statusPlayed");
    expect(statusLine(item("held"), "caregiver")).toBe("statusHeld");
    expect(statusLine(item("dismissed"), "caregiver")).toBe("statusDismissed");
  });

  it("never claims what a card became for anyone but his caregiver, and never for a duty card", () => {
    expect(statusLine(item("opened"), "helper")).toBeNull();
    expect(statusLine(item("opened", "duty"), "caregiver")).toBeNull();
  });

  it("says nothing rather than guess at a status the backend has not sent", () => {
    expect(statusLine(item("queued"), "caregiver")).toBeNull();
  });
});
