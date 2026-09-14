import type { ConditionOut } from "../api/types";

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
