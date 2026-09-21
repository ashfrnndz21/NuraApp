import { describe, expect, it } from "vitest";
import type { ConditionOut } from "../../src/api/types";
import { acknowledgementLine, asksFor, boost, cloudView, joinNames, sizeOf, toggle, topWords } from "../../src/onboarding/cloud";
import type { CloudWord } from "../../src/onboarding/cloud";

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
    expect(joinNames(["High blood pressure", "Cholesterol", "Sugar, diabetes"], " and ")).toBe(
      "High blood pressure, Cholesterol and Sugar, diabetes",
    );
  });

  it("never adds a space of its own — a language that wants none (Chinese) gets none", () => {
    expect(joinNames(["高血压", "胆固醇"], "和")).toBe("高血压和胆固醇");
  });
});

describe("acknowledgementLine", () => {
  const bubble = (name: string): CloudWord => ({ code: name, name, term: null, size: 1, picked: true, fresh: false });

  it("says nothing when nothing is picked", () => {
    expect(acknowledgementLine([], "You told me about {list}.", " and ")).toBeNull();
  });

  it("reads back exactly what he picked, in his own words — never a diagnosis", () => {
    const line = acknowledgementLine([bubble("High blood pressure"), bubble("Sugar, diabetes")], "You told me about {list}.", " and ");
    expect(line).toBe("You told me about High blood pressure and Sugar, diabetes.");
  });

  it("names a caregiver's patient rather than saying 'your'", () => {
    const line = acknowledgementLine([bubble("High blood pressure")], "Nura wrote down {list} for {name}.", " and ", { name: "Pa" });
    expect(line).toBe("Nura wrote down High blood pressure for Pa.");
    expect(line).not.toContain("your");
  });
});
