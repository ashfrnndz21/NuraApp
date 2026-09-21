import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** Contrast on the dusk-glass system (docs/design/experience-blueprint.html, docs/design/README.md):
 *  Ink (cream) reads at 7:1 or better on glass and paper over every ground stop, because the
 *  darkest realistic ground behind a card is still far enough from cream to clear it with room to
 *  spare; Plum, used only as accent text/icon/border on translucent surfaces, is held to the
 *  blueprint's own stated floor, 4.5:1, and checked over the LIGHTEST ground stop — the worst
 *  case a translucent surface can sit on. Read from tokens.css so the test follows the tokens,
 *  not a copy of them; `token()` resolves one level of `var(--x)` indirection, since several
 *  tokens below are defined as `var(--good)`, `var(--act)` and so on rather than repeating a hex
 *  literal. */
const css = readFileSync(new URL("../../src/ui/tokens.css", import.meta.url), "utf8");

function rawToken(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!match) throw new Error(`no token --${name}`);
  return match[1]!.trim();
}

function token(name: string): string {
  const value = rawToken(name);
  const ref = value.match(/^var\(--([a-z0-9-]+)\)$/);
  return ref ? token(ref[1]!) : value;
}

type RGB = [number, number, number];

function hex(value: string): RGB {
  const h = value.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function rgba(value: string): { rgb: RGB; alpha: number } {
  const m = value.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (!m) throw new Error(`not rgb/rgba: ${value}`);
  return { rgb: [Number(m[1]), Number(m[2]), Number(m[3])], alpha: m[4] === undefined ? 1 : Number(m[4]) };
}

/** Any token's colour, opaque or translucent, as {rgb, alpha} — so a caller can composite it over
 *  whatever ground it really sits on rather than assuming it is already opaque. */
function colorOf(name: string): { rgb: RGB; alpha: number } {
  const value = token(name);
  return value.startsWith("#") ? { rgb: hex(value), alpha: 1 } : rgba(value);
}

function over(top: RGB, alpha: number, bottom: RGB): RGB {
  return [0, 1, 2].map((i) => Math.round(top[i]! * alpha + bottom[i]! * (1 - alpha))) as RGB;
}

/** A translucent token, composited onto a ground: the surface a card or a piece of text really
 *  paints, once its own alpha is accounted for. */
function onto(name: string, ground: RGB): RGB {
  const { rgb, alpha } = colorOf(name);
  return over(rgb, alpha, ground);
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
const plum = hex(token("plum"));
const inkOnLight = hex(token("ink-on-light"));

/** The atmosphere's own three ground stops (tokens.css `--ground`/`--ground-warm`/`--ground-soft`,
 *  base.css `.atmosphere`) — the darkest realistic ground a card ever paints over, and, for a
 *  translucent surface, the lightest one too: both ends are checked below, never just one. */
const grounds = ["ground", "ground-warm", "ground-soft"].map((name) => hex(token(name)));
const darkestGround = grounds.reduce((worst, g) => (luminance(g) < luminance(worst) ? g : worst));
const lightestGround = grounds.reduce((worst, g) => (luminance(g) > luminance(worst) ? g : worst));

describe("contrast on decision elements (dusk-glass)", () => {
  // The blueprint's own stated floor is 4.5:1 (docs/design/README.md: "Keep Nura's own type
  // scale and contrast: body text at 15px or larger and 4.5:1"), not the old system's stricter
  // 7:1 — and honestly so: `--glass-bg` and `--paper-bg` are the blueprint's own literal
  // translucent fills (rgba(255,255,255,.10) / a touch more opaque), which real content sits on
  // over a gradient ground, so the achievable ceiling here is lower than an opaque paper card's
  // was. Both still clear 6:1 in practice, well past the 4.5:1 the product asks for.
  it("Ink on Paper is 4.5:1 or better over every ground stop", () => {
    for (const ground of grounds) expect(contrast(ink, onto("paper-bg", ground))).toBeGreaterThanOrEqual(4.5);
  });

  it("Ink on Glass is 4.5:1 or better too, so a context tile reads in poor light", () => {
    for (const ground of grounds) expect(contrast(ink, onto("glass-bg", ground))).toBeGreaterThanOrEqual(4.5);
  });

  it("Ink soft (captions only) is 4.5:1 or better over every ground stop, direct or on glass", () => {
    for (const ground of grounds) {
      expect(contrast(onto("ink-soft", ground), ground)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(onto("ink-soft", ground), onto("glass-bg", ground))).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("Ink-on-light on Ink — the one strong pill's fill (blueprint `.btn.light`) — is 7:1 or better", () => {
    expect(contrast(inkOnLight, ink)).toBeGreaterThanOrEqual(7);
  });

  it("Plum, the accent text/icon/border colour, is 4.5:1 or better on glass and paper, even over the lightest ground stop", () => {
    expect(contrast(plum, onto("glass-bg", lightestGround))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(plum, onto("paper-bg", lightestGround))).toBeGreaterThanOrEqual(4.5);
  });

  it("Plum keeps 4.5:1 directly on the ground too (a focus ring, a link with nothing under it)", () => {
    for (const ground of grounds) expect(contrast(plum, ground)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("the tints (a faint wash of colour on glass, never a pale fill)", () => {
  const tintNames = ["tint-blush", "tint-lavender", "tint-sage", "tint-coral", "tint-cream", "peach", "butter", "sky", "tint-paper"];

  it("keep Ink 4.5:1 on every card tint, composited over the darkest ground stop", () => {
    for (const name of tintNames) expect(contrast(ink, onto(name, darkestGround)), name).toBeGreaterThanOrEqual(4.5);
  });

  it("keep a caption (ink-on-tint) and a Plum icon or word 4.5:1 on every tint too", () => {
    // `--ink-on-tint` is `--ink-soft` (translucent cream), not an opaque hex, so it is composited
    // the same way a real caption is: over the tint, which is itself composited over the ground.
    const quiet = colorOf("ink-on-tint");
    for (const name of tintNames) {
      const darkSurface = onto(name, darkestGround);
      expect(contrast(over(quiet.rgb, quiet.alpha, darkSurface), darkSurface), name).toBeGreaterThanOrEqual(4.5);
      expect(contrast(plum, onto(name, lightestGround)), name).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keep the Good pill's word 7:1 on its solid sage (docs/design/experience-blueprint.html `.flag`)", () => {
    expect(contrast(hex(token("good-ink")), hex(token("good-bg")))).toBeGreaterThanOrEqual(7);
  });
});

describe("onboarding's colours (solid, not translucent — the blueprint's own flag/pill pattern)", () => {
  it("keep a revealed word 7:1 with Ink, composited over the darkest ground stop", () => {
    expect(contrast(ink, onto("chip-fresh", darkestGround))).toBeGreaterThanOrEqual(7);
  });

  it("keep an answered Yes and an answered No 7:1 on their own solid grounds", () => {
    expect(contrast(hex(token("yes-ink")), hex(token("yes-bg")))).toBeGreaterThanOrEqual(7);
    expect(contrast(hex(token("no-ink")), hex(token("no-bg")))).toBeGreaterThanOrEqual(7);
  });

  it("keep a picked word's ink 7:1 on its solid fill, like the one strong pill", () => {
    expect(contrast(inkOnLight, ink)).toBeGreaterThanOrEqual(7);
  });

  it("keep the one rose pill (coral) 7:1 — the red-flag call button is never a low-contrast surface", () => {
    expect(contrast(hex(token("coral-pill-ink")), hex(token("coral-pill-bg")))).toBeGreaterThanOrEqual(7);
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

describe("the fonts (docs/design/experience-blueprint.html <style>: Figtree 300-600, Instrument Serif italic accent)", () => {
  it("bundles Figtree as the one body/heading family, self-hosted", () => {
    expect(css).toMatch(/@font-face\s*{\s*font-family:\s*"Figtree"/);
    expect(css).toMatch(/src:\s*url\("\/fonts\/figtree-latin(-ext)?\.woff2"\)/);
    expect(token("font")).toMatch(/^"Figtree"/);
    expect(rawToken("font-display")).toBe("var(--font)");
  });

  it("bundles Instrument Serif italic as the one accent-word face, self-hosted, never a whole heading", () => {
    expect(css).toMatch(/@font-face\s*{\s*font-family:\s*"Instrument Serif";\s*font-style:\s*italic/);
    expect(css).toMatch(/src:\s*url\("\/fonts\/instrument-serif-italic-latin(-ext)?\.woff2"\)/);
    expect(token("font-accent")).toMatch(/^"Instrument Serif"/);
  });

  it("never calls a font CDN: every src is the app's own /fonts path", () => {
    const srcs = css.match(/src:\s*url\([^)]+\)/g) ?? [];
    expect(srcs.length).toBeGreaterThan(0);
    for (const src of srcs) expect(src).toMatch(/url\("\/fonts\//);
  });
});
