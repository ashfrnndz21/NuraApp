import { describe, expect, it } from "vitest";
import type { ConditionOut } from "../../src/api/types";
import { asksFor, boost, cloudView, sizeOf, toggle, topWords } from "../../src/onboarding/cloud";
import { conditionWords, TOP } from "../../src/api/mock/graph";

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
  it("lists the picked words with a follow-up, in pick order — none from #117 yet", () => {
    expect(codes(asksFor(GRAPH, ["statin", "bp", "bp_meds", "doc"]))).toEqual(["statin", "bp_meds", "doc"]);
    expect(asksFor(conditionWords(), [...TOP])).toEqual([]);
  });
});

describe("the mock graph: E01's own (#117 conditions.json)", () => {
  const graph = conditionWords();
  const byCode = new Map(graph.map((each) => [each.code, each]));

  it("names only words that exist, and marks exactly the top words", () => {
    for (const word of graph) for (const related of word.related) expect(byCode.has(related), `${word.code} → ${related}`).toBe(true);
    expect(graph.filter((each) => each.top).map((each) => each.code).sort()).toEqual([...TOP].sort());
  });

  it("puts at least four common words on the first screen, in his words, never codes", () => {
    expect(topWords(graph).filter((each) => each.weight === 3).length).toBeGreaterThanOrEqual(4);
    expect(byCode.get("high_blood_pressure")?.name).toBe("High blood pressure");
    for (const word of graph) expect(word.name, word.code).not.toBe(word.code);
  });
});
