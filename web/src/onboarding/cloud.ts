import type { ConditionOut } from "../api/types";
import { fill } from "../strings";

/** The word cloud's behaviour, apart from any screen: which words are showing, how big each
 *  one is, and in what order. Pure, so it is unit-tested (`tests/unit/cloud.test.ts`).
 *
 *  - The backend's graph (#117) gives every word a weight (1–3, how common it is), the words
 *    it is `related` to, and whether the cloud shows it first (`top`).
 *  - A word shows when it is a top word or when a picked word relates to it — a word may sit
 *    under two picked words (a kidney number under pressure and sugar).
 *  - Its size is its weight plus one for every picked word that relates to it, capped at 3.
 *  - The order never shuffles under his finger: top words heaviest first (the most common on
 *    the first screen), and the words a pick reveals straight after the word that revealed them.
 *  - Unpicking a word also unpicks what only it had revealed. */

export type Size = 1 | 2 | 3;

export interface CloudWord {
  code: string;
  name: string;
  /** The clinic's word, when the backend sends one (E01 does not model it yet). */
  term: string | null;
  size: Size;
  picked: boolean;
  /** Revealed by the last pick: drawn a little apart until he taps elsewhere. */
  fresh: boolean;
  /** Whether picking this word reveals anything under it — the one thing Nura's per-tap line
   *  needs to say "I added what often goes with it." truthfully, never guessed. */
  hasRelated: boolean;
}

export interface CloudOptions {
  /** Show the light top words too (weight 1). They sit behind "Show more words". */
  showAll: boolean;
  lastPicked: string | null;
}

function index(words: readonly ConditionOut[]): Map<string, ConditionOut> {
  return new Map(words.map((each) => [each.code, each]));
}

/** How many picked words point at this one. */
export function boost(words: readonly ConditionOut[], picked: readonly string[], code: string): number {
  const byCode = index(words);
  return picked.filter((each) => byCode.get(each)?.related.includes(code)).length;
}

export function sizeOf(weight: number, boosted: number): Size {
  return Math.max(1, Math.min(3, weight + boosted)) as Size;
}

/** The top words, heaviest first; words of the same weight keep the graph's order. */
export function topWords(words: readonly ConditionOut[]): ConditionOut[] {
  return words
    .map((word, position) => ({ word, position }))
    .filter(({ word }) => word.top)
    .sort((a, b) => b.word.weight - a.word.weight || a.position - b.position)
    .map(({ word }) => word);
}

export function cloudView(words: readonly ConditionOut[], picked: readonly string[], options: CloudOptions): CloudWord[] {
  const byCode = index(words);
  const chosen = new Set(picked);
  const counts = new Map<string, number>();
  for (const code of picked) for (const related of byCode.get(code)?.related ?? []) counts.set(related, (counts.get(related) ?? 0) + 1);
  const freshCodes = new Set(options.lastPicked ? byCode.get(options.lastPicked)?.related ?? [] : []);

  const out: CloudWord[] = [];
  const placed = new Set<string>();
  const place = (word: ConditionOut): void => {
    if (placed.has(word.code)) return;
    placed.add(word.code);
    out.push({
      code: word.code,
      name: word.name,
      term: word.term ?? null,
      size: sizeOf(word.weight, counts.get(word.code) ?? 0),
      picked: chosen.has(word.code),
      fresh: freshCodes.has(word.code) && !chosen.has(word.code),
      hasRelated: word.related.length > 0,
    });
    if (!chosen.has(word.code)) return;
    for (const related of word.related) {
      const next = byCode.get(related);
      if (next) place(next);
    }
  };
  for (const top of topWords(words)) {
    if (options.showAll || top.weight >= 2 || chosen.has(top.code)) place(top);
  }
  return out;
}

/** Tap a word: pick it, or unpick it and whatever only it had revealed. Pick order is kept. */
export function toggle(words: readonly ConditionOut[], picked: readonly string[], code: string): string[] {
  if (!picked.includes(code)) return [...picked, code];
  let next = picked.filter((each) => each !== code);
  const byCode = index(words);
  // Drop any picked word that is no longer showing: not a top word, and no picked word still
  // relates to it. Repeat, since dropping one can orphan its own reveals.
  for (;;) {
    const kept = next.filter((each) => {
      const word = byCode.get(each);
      if (!word) return false;
      if (word.top) return true;
      return next.some((other) => other !== each && byCode.get(other)?.related.includes(each));
    });
    if (kept.length === next.length) return kept;
    next = kept;
  }
}

/** The picked words that carry a follow-up question, in pick order (none until E01 models them). */
export function asksFor(words: readonly ConditionOut[], picked: readonly string[]): ConditionOut[] {
  const byCode = index(words);
  return picked.map((code) => byCode.get(code)).filter((word): word is ConditionOut => Boolean(word?.ask));
}

/** "Or just tell me": the codes `POST /onboarding/tell-me` tagged, folded into what is already
 *  picked — each once, already-picked ones kept where they were, new ones added at the end in
 *  the order the backend named them. Every code it names is already one of the cloud's own
 *  words (the backend's own guarantee), so nothing here checks the graph again. */
export function foldTold(picked: readonly string[], told: readonly string[]): string[] {
  const next = [...picked];
  for (const code of told) if (!next.includes(code)) next.push(code);
  return next;
}

/** A small, deterministic 0–1 value from a word's own code (FNV-ish string hash) — used only to
 *  vary each bubble's drift phase and duration a little in `Cloud.tsx`, so neighbours never
 *  move in lockstep like a table's rows. Not random: the same word always gets the same phase,
 *  so a re-render (a re-picked word, a re-fetch of the same graph) never makes the cloud
 *  visibly "jump" to a new arrangement. */
export function phaseOf(code: string): number {
  let hash = 0;
  for (let i = 0; i < code.length; i++) hash = (hash * 31 + code.charCodeAt(i)) >>> 0;
  return (hash % 1000) / 1000;
}

/** A word's circle, placed (docs/design/experience-blueprint.html `cloud` scene: a floating
 *  cloud of different-sized circles, not a grid). */
export interface CloudCircle extends CloudWord {
  /** Left edge, as a percentage of the pack's own reference width — a percentage, not a pixel,
   *  so the same pack reads right from the narrowest supported phone up (`Cloud.tsx` draws the
   *  container at its own real width; only the diameter below is ever a fixed pixel size). */
  leftPercent: number;
  /** Top edge, in px — the container's own height simply grows to fit, so this stays a real
   *  pixel measurement rather than a percentage of an unknown height. */
  top: number;
  diameter: number;
}

/** The diameter each size tier draws at, in px — the same three sizes `onboarding.css`'s
 *  `.word.bubble.s1/s2/s3` already give a bubble (`min-width`/`min-height`), read here once so
 *  the packer and the stylesheet never drift apart. This is the FLOOR a word's own weight asks
 *  for; `minDiameterFor` below can only ever grow it, to fit a word too long for it — the tier
 *  itself never shrinks, so size still reads as weight for every short word. */
export const CLOUD_DIAMETER: Record<Size, number> = { 1: 60, 2: 90, 3: 126 };

/** The narrowest width any supported viewport actually gives the cloud (360x640's screen: the
 *  phone's own `--space-3` gutter, base.css, taken off both sides of 360px) — the packer works
 *  against this fixed reference and reports positions as percentages, so it never has to read
 *  a real DOM width to lay a phone-sized cloud out safely; a wider phone just leaves more air
 *  on the right, never a collision. */
export const CLOUD_PACK_WIDTH = 320;

/** The bubble's own padding, both sides (`.word.bubble`, onboarding.css). */
const BUBBLE_PADDING = 12;

/** The font size a size tier draws its label at, in px — the LARGER of the two densities
 *  tokens.css ever sets (`--word-1/2/3` under `[data-density="patient"]`), since `packCloud`
 *  never knows which density is live and a caregiver's own smaller font then only ever has
 *  more room in the circle, never less. */
const TIER_FONT_PX: Record<Size, number> = { 1: 20, 2: 22, 3: 24 };

/** A conservative estimate of how wide a word draws, in px, at a given font size — never a real
 *  measurement (`canvas.measureText`, the usual way): this has to return the exact same number
 *  in the browser and in a headless unit test, where there is no canvas and no loaded font to
 *  measure against. `AVG_CHAR_WIDTH_EM` errs wide for a proportional sans font at this weight —
 *  a slightly bigger circle than the word strictly needs is a good trade against ever breaking
 *  a word mid-word again. A CJK "word" (`cloudView` never splits one on a space) draws wider a
 *  character, so it gets its own, larger, allowance. */
const AVG_CHAR_WIDTH_EM = 0.58;
const CJK_CHAR_WIDTH_EM = 1.05;
function estimateWordWidth(word: string, fontPx: number): number {
  const isCjk = /[぀-ヿ㐀-鿿]/.test(word);
  return word.length * fontPx * (isCjk ? CJK_CHAR_WIDTH_EM : AVG_CHAR_WIDTH_EM);
}

/** The widest single, unbreakable word in a label — `cloudView`'s own names sometimes carry
 *  more than one word ("High blood pressure"); wrapping happens at the spaces between them
 *  (`overflow-wrap: normal`/`word-break: keep-all`, onboarding.css), never inside one, so only
 *  the longest of them ever has to fit a circle's own width on one line. */
function longestWord(name: string): string {
  return name.split(/\s+/).reduce((longest, word) => (word.length > longest.length ? word : longest), "");
}

/** The smallest a circle can be and still hold this word's longest piece on one line, at that
 *  size tier's own (larger-density) font — with NO regard for the tier's usual size: this is
 *  the one true floor `packCloud`'s own scale-down (below) is never allowed to go under, for
 *  a short word too ("Weight" still needs some real width, just less than its tier gives it by
 *  default). */
function wordFitOnly(word: Pick<CloudWord, "name" | "size">): number {
  const widest = estimateWordWidth(longestWord(word.name), TIER_FONT_PX[word.size]);
  return Math.ceil(widest + BUBBLE_PADDING * 2);
}

/** The smallest a word's own circle can be and still hold its longest word on one line, AND
 *  read as its own weight tier's usual size — never below either: a short word still draws at
 *  its weight's usual size (`CLOUD_DIAMETER`); a long one grows past it, exactly as far as
 *  `wordFitOnly` says it must. */
export function minDiameterFor(word: Pick<CloudWord, "name" | "size">): number {
  return Math.max(CLOUD_DIAMETER[word.size], wordFitOnly(word));
}

/** One outward-ring search, in `view`'s own order, at whatever diameter `diameterOf` gives each
 *  word — the shared engine both passes of `packCloud` below run (once to measure, once for
 *  real), so the search itself only has to be written once. */
function ringPack(view: readonly CloudWord[], diameterOf: (word: CloudWord) => number): { circles: CloudCircle[]; height: number } {
  const placed: { x: number; y: number; r: number }[] = [];
  const circles: CloudCircle[] = [];
  const margin = 8;
  const centerX = CLOUD_PACK_WIDTH / 2;
  let bottom = 0;
  for (const word of view) {
    const diameter = diameterOf(word);
    const r = diameter / 2;
    const startAngle = phaseOf(word.code) * Math.PI * 2;
    let x = centerX;
    let y = r;
    let found = false;
    // Ring by ring, outward from the seed point: at each ring, enough angles are sampled that
    // neighbouring samples never sit more than roughly `r + margin` apart, so the search cannot
    // step clean over a gap that would actually have fit (`ringStep` sets how far apart the
    // rings themselves sit — small enough that two rings never leave an un-sampled band wider
    // than a circle either). A real word cloud tops out around 20-30 words, so this is a small
    // amount of arithmetic, never a visible pause.
    const ringStep = Math.max(6, r * 0.6);
    for (let radius = 0; radius <= CLOUD_PACK_WIDTH * 3 && !found; radius += ringStep) {
      const samples = radius === 0 ? 1 : Math.max(6, Math.ceil((2 * Math.PI * radius) / (r + margin)));
      for (let i = 0; i < samples; i++) {
        const theta = startAngle + (i / samples) * Math.PI * 2;
        const cx = centerX + Math.cos(theta) * radius;
        // Biased downward (never above the seed row) — `Math.abs` on the vertical term folds
        // the whole ring into the lower half-plane, so the cloud only ever grows the screen's
        // own scroll taller, never needs space above row 0 that `top: 0` has no room for.
        const cy = r + radius * 0.5 + Math.abs(Math.sin(theta)) * radius * 0.5;
        if (cx - r < 0 || cx + r > CLOUD_PACK_WIDTH) continue;
        // The real tap target is the button's own box (a square, `border-radius` only changes
        // how it paints), so two boxes count as touching the moment they are `r1 + r2 + margin`
        // apart on EITHER axis alone — a plain centre-to-centre distance still lets two large
        // circles' square corners clip each other even when the circles themselves clear
        // (found looking at this package's own captures against `cp5-onboarding.spec.ts`'s own
        // "never overlaps" geometry check, which measures exactly these boxes).
        const collides = placed.some((p) => Math.abs(p.x - cx) < p.r + r + margin && Math.abs(p.y - cy) < p.r + r + margin);
        if (!collides) {
          x = cx;
          y = cy;
          found = true;
          break;
        }
      }
    }
    if (!found) {
      // Never reached in practice (the ring search runs three screens deep before giving up),
      // but a placement that is never wrong beats one that is merely rare: a fresh row under
      // everything already placed is always free, by construction.
      x = Math.min(Math.max(centerX, r), CLOUD_PACK_WIDTH - r);
      y = (placed.length > 0 ? Math.max(...placed.map((p) => p.y + p.r)) : 0) + r + margin;
    }
    placed.push({ x, y, r });
    bottom = Math.max(bottom, y + r);
    circles.push({ ...word, leftPercent: ((x - r) / CLOUD_PACK_WIDTH) * 100, top: y - r, diameter });
  }
  return { circles, height: bottom + margin };
}

/** Places every word as a circle, none overlapping, in `view`'s own order (top words heaviest
 *  first, a pick's reveals right after it — `cloudView`, unchanged) so the cloud's DOM order,
 *  and so its Tab order, never depends on where a circle lands — a short outward spiral search
 *  from a seeded start point (the same technique word-cloud layouts use: try a point: on a
 *  collision, step further round and further out; `phaseOf(word.code)` seeds where each word's
 *  own spiral starts, so the same picks always draw the same cloud — no re-shuffle on an
 *  unrelated re-render).
 *
 *  Every circle is at least `minDiameterFor` its own word — never smaller, a word is never
 *  broken mid-word to fit a circle too small for it. If that alone would pack the cloud taller
 *  than a tier-sized pack would ever need by much, every circle ABOVE its own word's floor is
 *  scaled back down together, proportionally, toward that floor (never below it) until the
 *  height comes back within budget — a long word's own circle still only ever grows as far as
 *  it truly has to, and the ordinary short words around it shrink back toward their tier's own
 *  size rather than the whole cloud growing to match the one long word. Pure and deterministic,
 *  so it is unit-tested (`tests/unit/cloud.test.ts`) apart from ever measuring a real screen. */
export function packCloud(view: readonly CloudWord[]): { circles: CloudCircle[]; height: number } {
  if (view.length === 0) return { circles: [], height: 0 };
  const natural = ringPack(view, (word) => CLOUD_DIAMETER[word.size]);
  const target = new Map(view.map((word) => [word.code, minDiameterFor(word)]));
  const needed = ringPack(view, (word) => target.get(word.code) ?? CLOUD_DIAMETER[word.size]);
  const budget = Math.max(natural.height * 1.35, CLOUD_PACK_WIDTH);
  if (needed.height <= budget) return needed;
  // Over budget: every circle shrinks back toward its OWN word's true floor (`wordFitOnly` — no
  // tier included, so a long word's circle can give back exactly as much as its tier gave it
  // beyond what the word itself needs, never more) — proportional to how far over the budget
  // the pack ran against how much "give" exists across the whole cloud to take it from. A short
  // word already at its own floor already (`target === wordFitOnly`, `minDiameterFor`'s own
  // `Math.max`) has zero slack and does not move; a long word's circle only ever shrinks back
  // to the size its own word still needs, never past it.
  const floor = new Map(view.map((word) => [word.code, wordFitOnly(word)]));
  const totalSlack = view.reduce((sum, word) => sum + Math.max(0, (target.get(word.code) ?? 0) - (floor.get(word.code) ?? 0)), 0);
  const overBy = needed.height - budget;
  const shrinkFraction = totalSlack > 0 ? Math.min(1, overBy / totalSlack) : 0;
  return ringPack(view, (word) => {
    const t = target.get(word.code) ?? CLOUD_DIAMETER[word.size];
    const f = floor.get(word.code) ?? t;
    return Math.round(t - (t - f) * shrinkFraction);
  });
}

/** Nura's one line right under the cloud, changed in place on every tap
 *  (docs/design/onboarding-mock.html `pick()`'s own `cloudmsg`) — never a checklist, never an
 *  accumulating list of everything picked so far, just what this one tap did: picking a word
 *  that reveals others says so; picking one that reveals nothing just says it is noted;
 *  unpicking always reads the same sentence, whichever word it was. Each half below is its own
 *  string (docs/plain-words.md rule 2, one idea a line) and this only ever joins two of them
 *  with a space — never a third — so the checker and the read-aloud sentence agree without the
 *  source itself carrying two ideas on one line. */
export function tapHint(
  word: CloudWord,
  nowPicked: boolean,
  templates: { picked: string; added: string; removed: string; removedSub: string },
  slots: Record<string, string> = {},
): string {
  if (!nowPicked) return `${fill(templates.removed, slots)} ${templates.removedSub}`;
  const noted = fill(templates.picked, { ...slots, name: word.name });
  return word.hasRelated ? `${noted} ${templates.added}` : noted;
}

/** "A and B", "A, B and C" — the plain join every language reads the same way here (no serial
 *  comma). `and` is the whole connector as that language writes it, spaces included where it
 *  wants them (English " and ", Chinese bare "和" with none) — carried by the caller's own
 *  string, never added here, so the join stays correct however a language spaces it.
 *
 *  A name that already carries its own comma ("In hospital, last year") breaks the ", "/" and "
 *  list grammar — "A, B and In hospital, last year" reads as four things, not three. Operator
 *  review: rather than a clever nested-clause template (fragile across three languages), when
 *  ANY picked name has a comma in it the whole list falls back to semicolons throughout
 *  ("high blood pressure; high cholesterol; in hospital, last year") — plain, unambiguous, the
 *  same shape in every language. Pure and tiny on purpose: it never touches a word's own
 *  translation, only how the already-translated names are strung together
 *  (`tests/unit/cloud.test.ts`). */
export function joinNames(names: readonly string[], and: string): string {
  if (names.length === 0) return "";
  if (names.length === 1) return names[0]!;
  if (names.some((name) => name.includes(","))) return names.join("; ");
  return `${names.slice(0, -1).join(", ")}${and}${names[names.length - 1]}`;
}

/** A name read back mid-sentence, not at its own start, reads oddly capitalised ("You told me
 *  about High blood pressure and High cholesterol.") — every picked name in
 *  `acknowledgementLine`'s two templates sits after "about "/"wrote down ", never at the very
 *  start of the rendered sentence, so every one of them gets this. Left alone for a genuine
 *  acronym (2+ letters, entirely upper-case: "TB", "CPR") — lower-casing "Tb" would be wrong —
 *  and left alone entirely outside en/ms (zh has no letter case to change). No "proper noun"
 *  flag exists on `CloudWord` today; if the graph ever adds one, check it here first, before
 *  the acronym check. */
export function lowerFirst(name: string): string {
  if (!name) return name;
  const firstWord = name.split(/\s+/, 1)[0] ?? "";
  const isAcronym = firstWord.length >= 2 && firstWord === firstWord.toUpperCase() && firstWord !== firstWord.toLowerCase();
  if (isAcronym) return name;
  return name.charAt(0).toLowerCase() + name.slice(1);
}

/** Nura's one-line acknowledgement under the cloud (docs/design/experience-blueprint.html
 *  `cloud` scene note: never a diagnosis, only what he picked, read back in plain words — "You
 *  told me about your blood pressure and your sugar," never "You have hypertension"). Built
 *  from the same `CloudWord.name` every bubble already shows (never a code, never the clinic's
 *  own term), in the order he picked them; `null` when nothing is picked yet, so the caller
 *  shows nothing rather than an empty sentence. `lowercase`: en/ms only (`language.value !==
 *  "zh"`, `Cloud.tsx`) — see `lowerFirst`. */
export function acknowledgementLine(
  pickedWords: readonly CloudWord[],
  template: string,
  and: string,
  options: { slots?: Record<string, string>; lowercase?: boolean } = {},
): string | null {
  if (pickedWords.length === 0) return null;
  const names = pickedWords.map((word) => (options.lowercase ? lowerFirst(word.name) : word.name));
  const list = joinNames(names, and);
  return fill(template, { ...options.slots, list });
}
