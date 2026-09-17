import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** 7:1 on any decision element, in both densities: Ink on Paper over every wash stop, and
 *  white on Plum for the one filled button. Read from tokens.css so the test follows the
 *  tokens, not a copy of them. */
const css = readFileSync(new URL("../../src/ui/tokens.css", import.meta.url), "utf8");

function token(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!match) throw new Error(`no token --${name}`);
  return match[1]!.trim();
}

type RGB = [number, number, number];

function hex(value: string): RGB {
  const h = value.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function rgba(value: string): { rgb: RGB; alpha: number } {
  const m = value.match(/rgba\(\s*(\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/);
  if (!m) throw new Error(`not rgba: ${value}`);
  return { rgb: [Number(m[1]), Number(m[2]), Number(m[3])], alpha: Number(m[4]) };
}

function over(top: RGB, alpha: number, bottom: RGB): RGB {
  return [0, 1, 2].map((i) => Math.round(top[i]! * alpha + bottom[i]! * (1 - alpha))) as RGB;
}

function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: RGB, b: RGB): number {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (l1 + 0.05) / (l2 + 0.05);
}

const ink = hex(token("ink"));
const inkSoft = hex(token("ink-soft"));
const plum = hex(token("plum"));
const white: RGB = [255, 255, 255];
const paper = rgba(token("paper-bg"));
const glass = rgba(token("glass-bg"));
const washStops = ["lavender", "blush", "sage", "cream", "coral-wash", "coral-mid", "mist", "ground", "ground-warm", "ground-soft"].map((name) => hex(token(name)));

describe("contrast on decision elements", () => {
  it("Ink on Paper is 7:1 or better over every wash stop", () => {
    for (const stop of washStops) {
      const surface = over(paper.rgb, paper.alpha, stop);
      expect(contrast(ink, surface)).toBeGreaterThanOrEqual(7);
    }
  });

  it("white on Plum, the one filled button, is 7:1 or better", () => {
    expect(contrast(white, plum)).toBeGreaterThanOrEqual(7);
  });

  it("Plum text on Paper (links, the active tab) is 7:1 or better", () => {
    for (const stop of washStops) expect(contrast(plum, over(paper.rgb, paper.alpha, stop))).toBeGreaterThanOrEqual(7);
  });

  it("Ink on Glass is at least 7:1 too, so context tiles read in poor light", () => {
    for (const stop of washStops) expect(contrast(ink, over(glass.rgb, glass.alpha, stop))).toBeGreaterThanOrEqual(7);
  });

  it("Ink soft is caption-only: 4.5:1 on Paper, which is why it never carries a decision", () => {
    for (const stop of washStops) expect(contrast(inkSoft, over(paper.rgb, paper.alpha, stop))).toBeGreaterThanOrEqual(4.5);
  });
});

describe("the warm tints (docs/design-direction.md)", () => {
  const tints = ["blush", "lavender", "sage", "coral-wash", "cream", "peach", "butter", "sky", "tint-paper"].map((name) => [name, hex(token(name))] as const);
  const grounds = ["ground", "ground-warm", "ground-soft"].map((name) => [name, hex(token(name))] as const);

  it("keep Ink 7:1 on every card tint and every ground, so a decision may sit on any of them", () => {
    for (const [name, tint] of [...tints, ...grounds]) expect(contrast(ink, tint), name).toBeGreaterThanOrEqual(7);
  });

  it("keep a caption and a Plum icon or word 4.5:1 on every tint, in her density too", () => {
    const quiet = hex(token("ink-on-tint"));
    for (const [name, tint] of tints) {
      expect(contrast(quiet, tint), name).toBeGreaterThanOrEqual(4.5);
      expect(contrast(plum, tint), name).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keep Plum words and Ink soft captions readable on the ground", () => {
    for (const [name, ground] of grounds) {
      expect(contrast(plum, ground), name).toBeGreaterThanOrEqual(7);
      expect(contrast(inkSoft, ground), name).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keep the Good pill's word 7:1 on its green", () => {
    expect(contrast(hex(token("good-ink")), hex(token("good-bg")))).toBeGreaterThanOrEqual(7);
  });
});

describe("onboarding's colours", () => {
  it("keep a revealed word 7:1 with Ink on its tint", () => {
    expect(contrast(ink, hex(token("chip-fresh")))).toBeGreaterThanOrEqual(7);
  });

  it("keep an answered Yes and an answered No 7:1 on their own grounds", () => {
    expect(contrast(hex(token("yes-ink")), hex(token("yes-bg")))).toBeGreaterThanOrEqual(7);
    expect(contrast(hex(token("no-ink")), hex(token("no-bg")))).toBeGreaterThanOrEqual(7);
  });

  it("keep a picked word white on Plum, like the one filled button", () => {
    expect(contrast(white, plum)).toBeGreaterThanOrEqual(7);
  });
});

describe("the two densities", () => {
  const patient = css.slice(css.indexOf('[data-density="patient"]'), css.indexOf("The wash is the status"));
  const caregiver = css.slice(css.indexOf("Caregiver density"), css.indexOf("Patient density"));

  it("give the patient a 20px body, 56px targets and paper for every card", () => {
    expect(patient).toMatch(/--text-body:\s*1\.25rem/);
    expect(patient).toMatch(/--target:\s*56px/);
    expect(patient).toMatch(/--card-bg:\s*var\(--paper-bg\)/);
  });

  it("never size a word in the patient's cloud below his 20px body", () => {
    for (const size of [1, 2, 3]) {
      const rem = Number(patient.match(new RegExp(`--word-${size}:\\s*([\\d.]+)rem`))?.[1]);
      expect(rem, `--word-${size}`).toBeGreaterThanOrEqual(1.25);
    }
  });

  it("give the caregiver a 16px body, 48px targets and glass first", () => {
    expect(caregiver).toMatch(/--text-body:\s*1rem/);
    expect(caregiver).toMatch(/--target:\s*48px/);
    expect(caregiver).toMatch(/--card-bg:\s*var\(--glass-bg\)/);
  });

  it("honour Reduce Motion by zeroing every duration", () => {
    expect(css).toMatch(/prefers-reduced-motion: reduce[\s\S]*--settle:\s*0ms[\s\S]*--wash-fade:\s*0ms/);
  });

  it("use rem for every type size so the system text size scales it", () => {
    const sizes = css.match(/--text-[a-z-]+:\s*[^;]+;/g) ?? [];
    expect(sizes.length).toBeGreaterThan(5);
    for (const size of sizes) expect(size).toMatch(/rem/);
  });
});
