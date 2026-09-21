import { describe, expect, it } from "vitest";
import type { ConditionOut } from "../../src/api/types";
import { acknowledgementLine, asksFor, boost, cloudView, joinNames, lowerFirst, phaseOf, sizeOf, toggle, topWords } from "../../src/onboarding/cloud";
import type { CloudWord } from "../../src/onboarding/cloud";
import { en } from "../../src/strings/en";
import { ms } from "../../src/strings/ms";
import { zh } from "../../src/strings/zh";

const w = (code: string, weight: number, top: boolean, related: string[] = [], ask = false, term: string | null = null): ConditionOut => ({
  code,
  name: code.toUpperCase(),
  weight,
  related,
  top,
  term,
  ask: ask ? { question: `${code}?`, options: [{ id: "a", text: "A" }] } : null,
});

// A small graph in #117's shape: two common top words, one light one; "doc" under "bp" and "chol".
const GRAPH: ConditionOut[] = [
  w("thy", 1, true, ["thy_tabs"]),
  w("bp", 3, true, ["bp_meds", "doc", "kid"], false, "hypertension"),
  w("chol", 3, true, ["statin", "doc"]),
  w("sugar", 2, true, ["kid"]),
  w("heart", 2, true, ["hf"]),
  w("bp_meds", 2, false, [], true),
  w("doc", 1, false, [], true),
  w("kid", 1, false),
  w("statin", 2, false, [], true),
  w("thy_tabs", 1, false),
  w("hf", 2, false, ["water"]),
  w("water", 1, false),
];

const codes = (view: { code: string }[]) => view.map((each) => each.code);

describe("which words show, and in what order", () => {
  it("puts the common top words first, keeps the graph's order within a weight, and hides the light ones", () => {
    expect(codes(topWords(GRAPH))).toEqual(["bp", "chol", "sugar", "heart", "thy"]);
    expect(codes(cloudView(GRAPH, [], { showAll: false, lastPicked: null }))).toEqual(["bp", "chol", "sugar", "heart"]);
    expect(codes(cloudView(GRAPH, [], { showAll: true, lastPicked: null }))).toEqual(["bp", "chol", "sugar", "heart", "thy"]);
  });

  it("shows a light word he picked even behind 'Show more words'", () => {
    expect(codes(cloudView(GRAPH, ["thy"], { showAll: false, lastPicked: null }))).toContain("thy");
  });

  it("brings a pick's related words in straight after it, and never moves the words already there", () => {
    const before = codes(cloudView(GRAPH, [], { showAll: false, lastPicked: null }));
    const after = codes(cloudView(GRAPH, ["chol"], { showAll: false, lastPicked: "chol" }));
    expect(after).toEqual(["bp", "chol", "statin", "doc", "sugar", "heart"]);
    expect(after.filter((code) => before.includes(code))).toEqual(before);
  });

  it("places a word two picks point at once, after the first that revealed it", () => {
    const view = codes(cloudView(GRAPH, ["bp", "chol"], { showAll: false, lastPicked: "chol" }));
    expect(view.filter((code) => code === "doc")).toHaveLength(1);
    expect(view.indexOf("doc")).toBeLessThan(view.indexOf("chol"));
  });

  it("reveals a word two levels down only once the word above it is picked", () => {
    expect(codes(cloudView(GRAPH, ["heart"], { showAll: false, lastPicked: "heart" }))).not.toContain("water");
    expect(codes(cloudView(GRAPH, ["heart", "hf"], { showAll: false, lastPicked: "hf" }))).toContain("water");
  });

  it("carries the clinic's word only when the backend sends one", () => {
    const view = cloudView(GRAPH, ["bp"], { showAll: false, lastPicked: "bp" });
    expect(view.find((each) => each.code === "bp")?.term).toBe("hypertension");
    expect(view.find((each) => each.code === "chol")?.term).toBeNull();
  });
});

describe("re-weighting", () => {
  it("sizes a word by its commonness, plus one for each pick that points at it, capped at 3", () => {
    expect(sizeOf(1, 0)).toBe(1);
    expect(sizeOf(1, 1)).toBe(2);
    expect(sizeOf(2, 5)).toBe(3);
    const size = (picked: string[]) => cloudView(GRAPH, picked, { showAll: false, lastPicked: null }).find((each) => each.code === "doc")?.size;
    expect(size(["bp"])).toBe(2);
    expect(size(["bp", "chol"])).toBe(3);
    expect(boost(GRAPH, ["bp", "chol"], "doc")).toBe(2);
  });

  it("grows the kidney word when sugar is picked too", () => {
    const view = (picked: string[]) => cloudView(GRAPH, picked, { showAll: false, lastPicked: null });
    expect(view(["bp"]).find((each) => each.code === "kid")?.size).toBe(2);
    expect(view(["bp", "sugar"]).find((each) => each.code === "kid")?.size).toBe(3);
  });

  it("marks only the last pick's unpicked related words as fresh", () => {
    const fresh = cloudView(GRAPH, ["bp", "chol", "statin"], { showAll: false, lastPicked: "chol" }).filter((each) => each.fresh);
    expect(codes(fresh)).toEqual(["doc"]);
  });
});

describe("toggle", () => {
  it("adds a pick at the end, keeping the order he picked in", () => {
    expect(toggle(GRAPH, ["chol"], "bp")).toEqual(["chol", "bp"]);
  });

  it("unpicks a word and what only it had revealed", () => {
    expect(toggle(GRAPH, ["bp", "bp_meds", "doc"], "bp")).toEqual([]);
  });

  it("keeps a revealed word another pick still points at", () => {
    expect(toggle(GRAPH, ["bp", "chol", "doc"], "bp")).toEqual(["chol", "doc"]);
    expect(toggle(GRAPH, ["bp", "sugar", "kid"], "bp")).toEqual(["sugar", "kid"]);
  });

  it("follows the chain down: unpicking heart drops what only it revealed", () => {
    expect(toggle(GRAPH, ["heart", "hf", "water", "chol"], "heart")).toEqual(["chol"]);
  });
});

describe("asksFor", () => {
  it("lists the picked words with a follow-up, in pick order", () => {
    expect(codes(asksFor(GRAPH, ["statin", "bp", "bp_meds", "doc"]))).toEqual(["statin", "bp_meds", "doc"]);
  });
});

describe("joinNames", () => {
  it("joins nothing, one and two-or-more differently, spacing exactly as the connector carries it", () => {
    expect(joinNames([], " and ")).toBe("");
    expect(joinNames(["High blood pressure"], " and ")).toBe("High blood pressure");
    expect(joinNames(["High blood pressure", "Cholesterol"], " and ")).toBe("High blood pressure and Cholesterol");
    expect(joinNames(["High blood pressure", "Cholesterol", "Weight"], " and ")).toBe("High blood pressure, Cholesterol and Weight");
  });

  it("never adds a space of its own — a language that wants none (Chinese) gets none", () => {
    expect(joinNames(["高血压", "胆固醇"], "和")).toBe("高血压和胆固醇");
  });

  it("falls back to semicolons throughout when any one name already carries its own comma — the list grammar would otherwise read as one more item than he actually picked", () => {
    expect(joinNames(["High blood pressure", "Cholesterol", "In hospital, last year"], " and ")).toBe(
      "High blood pressure; Cholesterol; In hospital, last year",
    );
    // Even with exactly two names, and even when the comma is on the FIRST one, not the last.
    expect(joinNames(["In hospital, last year", "Weight"], " and ")).toBe("In hospital, last year; Weight");
  });

  it("a single comma-carrying name is returned as-is — nothing to join yet", () => {
    expect(joinNames(["In hospital, last year"], " and ")).toBe("In hospital, last year");
  });
});

describe("lowerFirst", () => {
  it("lower-cases an ordinary name's first letter, for a mid-sentence read", () => {
    expect(lowerFirst("High blood pressure")).toBe("high blood pressure");
    expect(lowerFirst("Cholesterol")).toBe("cholesterol");
  });

  it("leaves a genuine acronym alone — lower-casing 'Tb' would be wrong", () => {
    expect(lowerFirst("TB")).toBe("TB");
    expect(lowerFirst("CPR training")).toBe("CPR training");
  });

  it("leaves the empty string alone", () => {
    expect(lowerFirst("")).toBe("");
  });
});

describe("acknowledgementLine", () => {
  const bubble = (name: string): CloudWord => ({ code: name, name, term: null, size: 1, picked: true, fresh: false });

  it("says nothing when nothing is picked", () => {
    expect(acknowledgementLine([], "You told me about {list}.", " and ")).toBeNull();
  });

  it("reads back exactly what he picked, in his own words — never a diagnosis", () => {
    const line = acknowledgementLine([bubble("High blood pressure"), bubble("Cholesterol")], "You told me about {list}.", " and ", {
      lowercase: true,
    });
    expect(line).toBe("You told me about high blood pressure and cholesterol.");
  });

  it("names a caregiver's patient rather than saying 'your'", () => {
    const line = acknowledgementLine([bubble("High blood pressure")], "Nura wrote down {list} for {name}.", " and ", {
      slots: { name: "Pa" },
      lowercase: true,
    });
    expect(line).toBe("Nura wrote down high blood pressure for Pa.");
    expect(line).not.toContain("your");
  });

  it("lower-cases every name mid-sentence, none of them sits first in the rendered sentence", () => {
    const line = acknowledgementLine([bubble("High blood pressure"), bubble("Cholesterol"), bubble("Weight")], "You told me about {list}.", " and ", {
      lowercase: true,
    });
    expect(line).toBe("You told me about high blood pressure, cholesterol and weight.");
  });

  it("keeps an acronym's own case even mid-sentence", () => {
    const line = acknowledgementLine([bubble("TB")], "You told me about {list}.", " and ", { lowercase: true });
    expect(line).toBe("You told me about TB.");
  });

  it("without `lowercase` (zh has no case to change), a name's own case is kept exactly", () => {
    const line = acknowledgementLine([bubble("高血压"), bubble("胆固醇")], "您告诉我：{list}。", "和");
    expect(line).toBe("您告诉我：高血压和胆固醇。");
  });

  it("still falls back to semicolons when a picked name carries its own comma, whether or not names are lower-cased", () => {
    const withCase = acknowledgementLine(
      [bubble("High blood pressure"), bubble("Cholesterol"), bubble("In hospital, last year")],
      "You told me about {list}.",
      " and ",
      { lowercase: true },
    );
    expect(withCase).toBe("You told me about high blood pressure; cholesterol; in hospital, last year.");
  });

  // Both rules, in en, ms and zh, in the owner's own voice and the caregiver's — the exact
  // catalogue templates and connectors each language ships (`strings/{en,ms,zh}.ts`
  // `onboarding.cloud.ackSelf`/`ackOther`/`and`), not a copy of them, so a future wording change
  // that breaks this composition fails here first.
  const CATALOGUES = [
    { code: "en", s: en, lowercase: true },
    { code: "ms", s: ms, lowercase: true },
    { code: "zh", s: zh, lowercase: false },
  ] as const;

  for (const { code, s, lowercase } of CATALOGUES) {
    const c = s.onboarding.cloud;

    it(`${code}, the owner's own voice`, () => {
      const line = acknowledgementLine([bubble("High blood pressure")], c.ackSelf, c.and, { lowercase });
      expect(line).toBeTruthy();
      expect(line).toContain(lowercase ? "high blood pressure" : "High blood pressure");
    });

    it(`${code}, the caregiver's voice — names the patient, never "your"`, () => {
      const line = acknowledgementLine([bubble("High blood pressure")], c.ackOther, c.and, { slots: { name: "Pa" }, lowercase });
      expect(line).toBeTruthy();
      expect(line).toContain("Pa");
      expect(line).not.toMatch(/\byour\b/i);
    });

    it(`${code}, a comma-carrying name falls back to semicolons in both voices`, () => {
      const names = [bubble("High blood pressure"), bubble("In hospital, last year")];
      const self = acknowledgementLine(names, c.ackSelf, c.and, { lowercase })!;
      const other = acknowledgementLine(names, c.ackOther, c.and, { slots: { name: "Pa" }, lowercase })!;
      expect(self).toContain("; ");
      expect(other).toContain("; ");
    });
  }
});

describe("phaseOf", () => {
  it("is deterministic — the same code always gets the same phase", () => {
    expect(phaseOf("high_blood_pressure")).toBe(phaseOf("high_blood_pressure"));
  });

  it("stays within 0–1", () => {
    for (const code of ["a", "high_blood_pressure", "in_hospital_last_year", ""]) {
      const phase = phaseOf(code);
      expect(phase).toBeGreaterThanOrEqual(0);
      expect(phase).toBeLessThan(1);
    }
  });

  it("varies between different codes — the whole point is neighbours do not move in lockstep", () => {
    const phases = new Set(["high_blood_pressure", "cholesterol", "diabetes", "heart"].map(phaseOf));
    expect(phases.size).toBeGreaterThan(1);
  });
});
