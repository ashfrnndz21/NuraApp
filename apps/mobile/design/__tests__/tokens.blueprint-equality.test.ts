/**
 * Section 35: design/{motion,colors}.ts must equal the values in
 * `experience-blueprint-v2.html`'s `:root` block (the motion tokens) and
 * its `.phone`/`.atmos` rules (the product's own colour world — see
 * DESIGN_SYSTEM.md's naming caution: the file's outer `:root` also
 * carries an unrelated documentation-chrome palette, deliberately not
 * checked here).
 *
 * This test reads the HTML source directly and parses just enough CSS to
 * extract the values — no CSS parser dependency, the grammar here is a
 * handful of known, flat declarations.
 */
import fs from 'fs';
import path from 'path';

import { motionTokens, type Bezier } from '../motion';
import { phoneTokens } from '../colors';

const HTML_PATH = path.join(__dirname, '../../../../docs/design/experience-blueprint-v2.html');
const html = fs.readFileSync(HTML_PATH, 'utf8');

/** ms out of a CSS time literal (`140ms`, `7s`) or a bare number (`.985`). */
function parseCssNumber(raw: string): number {
  const v = raw.trim();
  if (v.endsWith('ms')) return parseFloat(v);
  if (v.endsWith('s')) return parseFloat(v) * 1000;
  return parseFloat(v);
}

/** Parse a flat `--name:value;--name2:value2;` block (no nested braces) into a Map. */
function parseDeclarations(block: string): Map<string, string> {
  const map = new Map<string, string>();
  const re = /--([a-z0-9-]+)\s*:\s*([^;]+);?/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(block))) {
    map.set(m[1], m[2].trim());
  }
  return map;
}

/**
 * Resolve a motion `:root` value to the duration in ms this project cares
 * about. Composite values (`520ms var(--spring-gentle)`) take the first
 * token; a bare `var(--other)` resolves against the same declaration map
 * (every referenced token is declared earlier in the same block).
 */
function resolveDurationMs(value: string, raw: Map<string, string>): number {
  const firstToken = value.trim().split(/\s+/)[0];
  const varMatch = firstToken.match(/^var\(--([a-z0-9-]+)\)$/);
  if (varMatch) {
    const referenced = raw.get(varMatch[1]);
    if (referenced === undefined) throw new Error(`unresolved var(--${varMatch[1]})`);
    return resolveDurationMs(referenced, raw);
  }
  return parseCssNumber(firstToken);
}

function parseBezier(value: string): Bezier {
  const m = value.match(/cubic-bezier\(([^)]+)\)/);
  if (!m) throw new Error(`not a cubic-bezier(): ${value}`);
  const nums = m[1].split(',').map((n) => parseFloat(n.trim()));
  if (nums.length !== 4) throw new Error(`cubic-bezier needs 4 numbers: ${value}`);
  return nums as unknown as Bezier;
}

// ---- extract the first, unscoped `:root{...}` block — the motion tokens ----
// (the file's *second* `:root{...}` is the unrelated documentation-chrome
// palette; DESIGN_SYSTEM.md's naming caution explains why they're not the
// same world and only the first is the product's own).
const rootBlocks = [...html.matchAll(/:root\{([\s\S]*?)\}/g)];
if (rootBlocks.length === 0) throw new Error('no :root{...} block found in experience-blueprint-v2.html');
const motionDecls = parseDeclarations(rootBlocks[0][1]);

// Keys that are not motion durations/curves (skipped from the loop below).
const NON_DURATION_KEYS = new Set(['press-in-ease']);
// Keys whose value is a plain factor, not a duration (scale-press).
const FACTOR_KEYS = new Set(['scale-press']);
const BEZIER_KEYS = new Set(['spring-gentle', 'spring-standard', 'spring-bouncy']);

describe('design/motion.ts equals experience-blueprint-v2.html :root', () => {
  test('every blueprint --custom-property this app names is declared', () => {
    for (const key of Object.keys(motionTokens)) {
      if (NON_DURATION_KEYS.has(key)) continue;
      expect(motionDecls.has(key)).toBe(true);
    }
  });

  test.each(Object.keys(motionTokens).filter((k) => !NON_DURATION_KEYS.has(k)))(
    '--%s matches',
    (key) => {
      const cssValue = motionDecls.get(key);
      expect(cssValue).toBeDefined();
      const ours = (motionTokens as Record<string, number | Bezier>)[key];
      if (BEZIER_KEYS.has(key)) {
        expect(parseBezier(cssValue as string)).toEqual(ours);
      } else if (FACTOR_KEYS.has(key)) {
        expect(parseFloat(cssValue as string)).toBeCloseTo(ours as number, 5);
      } else {
        expect(resolveDurationMs(cssValue as string, motionDecls)).toBeCloseTo(ours as number, 5);
      }
    },
  );
});

// ---- extract `.phone{...}` (ink/glass tokens) and `.atmos`/`.atmos i.*` (ground) ----
function firstRuleBody(selectorRe: RegExp): string {
  const m = html.match(selectorRe);
  if (!m) throw new Error(`selector not found: ${selectorRe}`);
  return m[1];
}

const phoneBlock = firstRuleBody(/\.phone\{([^}]*)\}/);
const phoneDecls = parseDeclarations(phoneBlock);

const atmosBlock = firstRuleBody(/(?<!\.phone\.alarm )\.atmos\{([^}]*)\}/);
const atmosGradientMatch = atmosBlock.match(/linear-gradient\(([^)]+)\)/);
if (!atmosGradientMatch) throw new Error('.atmos has no linear-gradient()');
const atmosGradientParts = atmosGradientMatch[1].split(',').map((p) => p.trim());
const atmosAngleDeg = parseFloat(atmosGradientParts[0]);
const atmosStops = atmosGradientParts.slice(1).map((p) => p.split(/\s+/)[0]);

function atmosLayer(letter: 'a' | 'b' | 'c') {
  const block = firstRuleBody(new RegExp(`\\.atmos i\\.${letter}\\{([^}]*)\\}`));
  const decls = parseDeclarations('--x:0;' + block.replace(/([a-z-]+):/g, (mm, p) => `--${p}:`));
  return {
    color: decls.get('background') ?? '',
    opacity: parseFloat(decls.get('opacity') ?? 'NaN'),
    animated: /animation\s*:/.test(block),
  };
}

describe('design/colors.ts equals experience-blueprint-v2.html .phone / .atmos', () => {
  test('ink / glass fill / glass border (--c / --g / --gb)', () => {
    expect(phoneDecls.get('c')).toBe(phoneTokens.c);
    // CSS writes `.10`/`.22`, our token writes `0.10`/`0.22` — compare as rgba strings loosely.
    expect(phoneDecls.get('g')?.replace(/\s/g, '')).toBe(
      phoneTokens.g.replace('0.10', '.10').replace(/\s/g, ''),
    );
    expect(phoneDecls.get('gb')?.replace(/\s/g, '')).toBe(
      phoneTokens.gb.replace('0.22', '.22').replace(/\s/g, ''),
    );
  });

  test('atmosphere gradient: angle + three stops', () => {
    expect(atmosAngleDeg).toBe(phoneTokens.atmosGradientAngleDeg);
    expect(atmosStops).toEqual([...phoneTokens.atmosGradient]);
  });

  test('atmosphere layer A (drifting)', () => {
    const a = atmosLayer('a');
    expect(a.color).toBe(phoneTokens.atmosLayerA.color);
    expect(a.opacity).toBeCloseTo(phoneTokens.atmosLayerA.opacity, 5);
    expect(a.animated).toBe(phoneTokens.atmosLayerA.animated);
  });

  test('atmosphere layer B (drifting, reverse)', () => {
    const b = atmosLayer('b');
    expect(b.color).toBe(phoneTokens.atmosLayerB.color);
    expect(b.opacity).toBeCloseTo(phoneTokens.atmosLayerB.opacity, 5);
    expect(b.animated).toBe(phoneTokens.atmosLayerB.animated);
  });

  test('atmosphere layer C (static — the third layer missing from the spike)', () => {
    const c = atmosLayer('c');
    expect(c.color).toBe(phoneTokens.atmosLayerC.color);
    expect(c.opacity).toBeCloseTo(phoneTokens.atmosLayerC.opacity, 5);
    expect(c.animated).toBe(phoneTokens.atmosLayerC.animated);
    expect(c.animated).toBe(false);
  });
});
