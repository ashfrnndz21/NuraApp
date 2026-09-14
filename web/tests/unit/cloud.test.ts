import { describe, expect, it } from "vitest";
import type { ConditionWordOut } from "../../src/api/types";
import { asksFor, boost, cloudView, sizeOf, toggle, topWords } from "../../src/onboarding/cloud";
import { conditionWords } from "../../src/api/mock/graph";

const w = (id: string, weight: 1 | 2 | 3, parent: string | null, related: string[] = [], ask = false): ConditionWordOut => ({
  id,
  word: id.toUpperCase(),
  term: null,
  weight,
  parent,
  related,
  ask: ask ? { question: `${id}?`, options: [{ id: "a", text: "A" }] } : null,
});

// A small graph: two common top words, one light one; "doc" hangs off both "bp" and "chol".
const GRAPH: ConditionWordOut[] = [
  w("thy", 1, null, ["thy_tabs"]),
  w("bp", 3, null, ["bp_meds", "doc", "kid"]),
  w("chol", 3, null, ["statin", "doc"]),
  w("sugar", 2, null, ["kid"]),
  w("heart", 2, null, ["hf"]),
  w("bp_meds", 2, "bp", [], true),
  w("doc", 1, "bp", [], true),
  w("kid", 1, "bp"),
  w("statin", 2, "chol", [], true),
  w("thy_tabs", 1, "thy"),
  w("hf", 2, "heart", ["water"]),
  w("water", 1, "hf"),
];

const ids = (view: { id: string }[]) => view.map((each) => each.id);

describe("which words show, and in what order", () => {
  it("puts the common top words first, keeps the graph's order within a weight, and hides the light ones", () => {
    expect(ids(topWords(GRAPH))).toEqual(["bp", "chol", "sugar", "heart", "thy"]);
    expect(ids(cloudView(GRAPH, [], { showAll: false, lastPicked: null }))).toEqual(["bp", "chol", "sugar", "heart"]);
    expect(ids(cloudView(GRAPH, [], { showAll: true, lastPicked: null }))).toEqual(["bp", "chol", "sugar", "heart", "thy"]);
  });

  it("shows a light word he picked even behind 'Show more words'", () => {
    expect(ids(cloudView(GRAPH, ["thy"], { showAll: false, lastPicked: null }))).toContain("thy");
  });

  it("brings a pick's related words in straight after it, and never moves the words already there", () => {
    const before = ids(cloudView(GRAPH, [], { showAll: false, lastPicked: null }));
    const after = ids(cloudView(GRAPH, ["chol"], { showAll: false, lastPicked: "chol" }));
    expect(after).toEqual(["bp", "chol", "statin", "doc", "sugar", "heart"]);
    expect(after.filter((id) => before.includes(id))).toEqual(before);
  });

  it("places a word shared by two picks once, after the first that revealed it", () => {
    const view = ids(cloudView(GRAPH, ["bp", "chol"], { showAll: false, lastPicked: "chol" }));
    expect(view.filter((id) => id === "doc")).toHaveLength(1);
    expect(view.indexOf("doc")).toBeLessThan(view.indexOf("chol"));
  });

  it("reveals a word two levels down only once its parent is picked", () => {
    expect(ids(cloudView(GRAPH, ["heart"], { showAll: false, lastPicked: "heart" }))).not.toContain("water");
    expect(ids(cloudView(GRAPH, ["heart", "hf"], { showAll: false, lastPicked: "hf" }))).toContain("water");
  });
});

describe("re-weighting", () => {
  it("sizes a word by its commonness, plus one for each pick that points at it, capped at 3", () => {
    expect(sizeOf(1, 0)).toBe(1);
    expect(sizeOf(1, 1)).toBe(2);
    expect(sizeOf(2, 5)).toBe(3);
    const size = (picked: string[]) => cloudView(GRAPH, picked, { showAll: false, lastPicked: null }).find((each) => each.id === "doc")?.size;
    expect(size(["bp"])).toBe(2);
    expect(size(["bp", "chol"])).toBe(3);
    expect(boost(GRAPH, ["bp", "chol"], "doc")).toBe(2);
  });

  it("grows 'kid' when sugar is picked too, the way kidneys go with pressure and sugar", () => {
    const view = (picked: string[]) => cloudView(GRAPH, picked, { showAll: false, lastPicked: null });
    expect(view(["bp"]).find((each) => each.id === "kid")?.size).toBe(2);
    expect(view(["bp", "sugar"]).find((each) => each.id === "kid")?.size).toBe(3);
  });

  it("marks only the last pick's unpicked related words as fresh", () => {
    const view = cloudView(GRAPH, ["bp", "chol", "statin"], { showAll: false, lastPicked: "chol" });
    const fresh = view.filter((each) => each.fresh).map((each) => each.id);
    expect(fresh).toEqual(["doc"]);
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

  it("follows the chain down: unpicking heart drops the weak heart and the water pill", () => {
    expect(toggle(GRAPH, ["heart", "hf", "water", "chol"], "heart")).toEqual(["chol"]);
  });
});

describe("asksFor", () => {
  it("lists the picked words with a follow-up, in pick order", () => {
    expect(ids(asksFor(GRAPH, ["statin", "bp", "bp_meds", "doc"]))).toEqual(["statin", "bp_meds", "doc"]);
  });
});

describe("the mock graph (the stand-in for E01's)", () => {
  const graph = conditionWords();
  const byId = new Map(graph.map((each) => [each.id, each]));

  it("names only words that exist, and gives every revealed word a parent", () => {
    for (const word of graph) for (const related of word.related) expect(byId.has(related), `${word.id} → ${related}`).toBe(true);
    for (const word of graph) if (word.parent) expect(byId.get(word.parent)!.related).toContain(word.id);
  });

  it("has at least four common top words for the first screen", () => {
    expect(topWords(graph).filter((each) => each.weight === 3).length).toBeGreaterThanOrEqual(4);
  });

  it("never puts the clinic's term where the plain word goes", () => {
    for (const word of graph) if (word.term) expect(word.word.toLowerCase()).not.toBe(word.term.toLowerCase());
  });
});
