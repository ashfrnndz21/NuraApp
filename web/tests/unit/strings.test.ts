import { describe, expect, it } from "vitest";
import { en } from "../../src/strings/en";
import { ms } from "../../src/strings/ms";
import { zh } from "../../src/strings/zh";
import { deviceLanguage, fill, LANGUAGES, refusalSentence, stringsFor } from "../../src/strings";

function leaves(value: unknown, path = ""): [string, string][] {
  if (typeof value === "string") return [[path, value]];
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, child]) => leaves(child, path ? `${path}.${key}` : key));
  }
  return [];
}

describe("the three catalogues", () => {
  it("have the same keys, so no language falls back to another", () => {
    const keys = (catalogue: unknown) => leaves(catalogue).map(([path]) => path).sort();
    expect(keys(ms)).toEqual(keys(en));
    expect(keys(zh)).toEqual(keys(en));
  });

  it("have a non-empty line for every key", () => {
    for (const catalogue of [en, ms, zh]) {
      for (const [path, text] of leaves(catalogue)) expect(text.trim(), path).not.toBe("");
    }
  });

  it("carry the same slots in every language", () => {
    const slots = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();
    const byPath = new Map(leaves(en));
    for (const catalogue of [ms, zh]) {
      for (const [path, text] of leaves(catalogue)) expect(slots(text), path).toEqual(slots(byPath.get(path) ?? ""));
    }
  });

  it("never show a red word", () => {
    const red = /\b(missed|failed|overdue|non-compliant|dose|recheck|follow-up|flag|log)\b/i;
    for (const [path, text] of leaves(en)) expect(text, path).not.toMatch(red);
  });
});

describe("fill", () => {
  it("fills only the slots a whole line already has", () => {
    expect(fill("Good morning, {name}.", { name: "Pa" })).toBe("Good morning, Pa.");
    expect(fill("You have taken your tablets on {count} days.", { count: 41 })).toBe(
      "You have taken your tablets on 41 days.",
    );
    expect(fill("{name} made this for you.", {})).toBe("{name} made this for you.");
  });
});

describe("deviceLanguage", () => {
  it("takes the first language Nura speaks, else English", () => {
    expect(deviceLanguage(["zh-Hans-SG", "en-SG"])).toBe("zh");
    expect(deviceLanguage(["ms-MY"])).toBe("ms");
    expect(deviceLanguage(["ta-SG", "fr"])).toBe("en");
    expect(deviceLanguage([])).toBe("en");
  });
});

describe("stringsFor", () => {
  it("answers every language the picker offers", () => {
    for (const code of LANGUAGES) expect(stringsFor(code).tabs.today).toBeTruthy();
    expect(refusalSentence("NoSession", "ms")).toBe(ms.refusals.NoSession);
  });
});
