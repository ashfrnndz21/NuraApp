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
