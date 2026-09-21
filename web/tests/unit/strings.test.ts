import { describe, expect, it } from "vitest";
import { en } from "../../src/strings/en";
import { ms } from "../../src/strings/ms";
import { zh } from "../../src/strings/zh";
import { readdirSync, readFileSync } from "node:fs";
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

describe("onboarding's words", () => {
  const fixtures = new URL("../../../backend/tests/fixtures/paper/", import.meta.url);
  const papers = readdirSync(fixtures)
    .filter((name) => name.endsWith(".json"))
    .map((name) => JSON.parse(readFileSync(new URL(name, fixtures), "utf8")) as { fields: { subject: string; attribute: string }[] });

  it("name every line the paper fixtures can put on a review card, in every language", () => {
    expect(papers.length).toBeGreaterThan(0);
    // A pharmacy receipt's line subjects are numbered in the order printed (`item_1`,
    // `item_2`…) and share one set of words (`fieldLabel`'s own `ITEM_SUBJECT` rule).
    const subjectWords = (subject: string) => (/^item_\d+$/.test(subject) ? "item" : subject);
    for (const code of LANGUAGES) {
      for (const paper of papers) {
        for (const field of paper.fields) {
          // `attribute === "other"` is the vocabulary's own escape hatch (E02 defect #1): a
          // line genuinely outside it has no canonical label by design — `fieldLabel` falls
          // back to the paper's own `label_on_paper` for it instead, never the catalogue.
          if (field.attribute === "other") continue;
          expect(
            stringsFor(code).onboarding.fields[subjectWords(field.subject)]?.[field.attribute],
            `${code} ${field.subject}.${field.attribute}`,
          ).toBeTruthy();
        }
      }
    }
  });

  it("say the self and other lines with the name slot only where a name belongs", () => {
    const about = en.onboarding.about;
    for (const [key, text] of Object.entries(about)) {
      if (typeof text !== "string") continue;
      if (key.endsWith("Self")) expect(text, key).not.toContain("{name}");
    }
    expect(fill(about.switchOther.large_text, { name: "Pa" })).toBe("Would bigger writing help Pa?");
  });

  it("use 'papers', never 'record', in Malay and Chinese as in English", () => {
    for (const [path, text] of leaves(ms.onboarding)) expect(text, path).not.toMatch(/rekod/i);
    for (const [path, text] of leaves(zh.onboarding)) expect(text, path).not.toMatch(/记录/);
  });
});
