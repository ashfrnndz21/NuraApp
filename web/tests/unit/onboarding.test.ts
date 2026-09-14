import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isPdf } from "../../src/onboarding/actions";

describe("papers", () => {
  it("sends a PDF to /imports and anything else to /photos", () => {
    expect(isPdf({ type: "application/pdf", name: "letter" })).toBe(true);
    expect(isPdf({ type: "", name: "LETTER.PDF" })).toBe(true);
    expect(isPdf({ type: "image/jpeg", name: "label.jpg" })).toBe(false);
  });
});

describe("nothing of onboarding is kept on the phone", () => {
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? files(path) : [path];
    });
  const root = new URL("../../src/", import.meta.url).pathname;
  const onboarding = [...files(join(root, "onboarding")), ...files(join(root, "screens/onboarding"))];

  it("has no browser storage and no key-value store anywhere in the onboarding code", () => {
    expect(onboarding.length).toBeGreaterThan(10);
    for (const path of onboarding) {
      const code = readFileSync(path, "utf8").replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
      expect(code, path).not.toMatch(/localStorage|sessionStorage|indexedDB|kvSet|kvGet|caches\./);
    }
  });
});
