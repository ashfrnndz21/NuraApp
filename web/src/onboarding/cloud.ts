import type { ConditionWordOut } from "../api/types";

/** The word cloud's behaviour, apart from any screen: which words are showing, how big each
 *  one is, and in what order. Pure, so it is unit-tested (`tests/unit/cloud.test.ts`).
 *
 *  - The backend's graph gives every word a weight (1–3, how common it is) and the words it
 *    is `related` to. A top word has no `parent`.
 *  - A word shows when it is a top word or when a picked word relates to it.
 *  - Its size is its weight plus one for every picked word that relates to it, capped at 3:
 *    picking "High blood pressure" and "Cholesterol" makes "I see a heart doctor" big.
 *  - The order never shuffles under his finger. Top words go heaviest first (so the most
 *    common ones are on the first screen, above the fold), and the words a pick reveals go
 *    straight after the word that revealed them.
 *  - Unpicking a word also unpicks what only it had revealed. */

export type Size = 1 | 2 | 3;

export interface CloudWord {
  id: string;
  word: string;
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

function index(words: readonly ConditionWordOut[]): Map<string, ConditionWordOut> {
  return new Map(words.map((each) => [each.id, each]));
}

/** How many picked words point at this one. */
export function boost(words: readonly ConditionWordOut[], picked: readonly string[], id: string): number {
  const byId = index(words);
  return picked.filter((each) => byId.get(each)?.related.includes(id)).length;
}

export function sizeOf(weight: number, boosted: number): Size {
  return Math.max(1, Math.min(3, weight + boosted)) as Size;
}

/** The top words, heaviest first; words of the same weight keep the graph's order. */
export function topWords(words: readonly ConditionWordOut[]): ConditionWordOut[] {
  return words
    .map((word, position) => ({ word, position }))
    .filter(({ word }) => word.parent === null)
    .sort((a, b) => b.word.weight - a.word.weight || a.position - b.position)
    .map(({ word }) => word);
}

export function cloudView(
  words: readonly ConditionWordOut[],
  picked: readonly string[],
  options: CloudOptions,
): CloudWord[] {
  const byId = index(words);
  const chosen = new Set(picked);
  const counts = new Map<string, number>();
  for (const id of picked) for (const related of byId.get(id)?.related ?? []) counts.set(related, (counts.get(related) ?? 0) + 1);
  const freshIds = new Set(options.lastPicked ? byId.get(options.lastPicked)?.related ?? [] : []);

  const out: CloudWord[] = [];
  const placed = new Set<string>();
  const place = (word: ConditionWordOut): void => {
    if (placed.has(word.id)) return;
    placed.add(word.id);
    out.push({
      id: word.id,
      word: word.word,
      term: word.term,
      size: sizeOf(word.weight, counts.get(word.id) ?? 0),
      picked: chosen.has(word.id),
      fresh: freshIds.has(word.id) && !chosen.has(word.id),
    });
    if (!chosen.has(word.id)) return;
    for (const related of word.related) {
      const next = byId.get(related);
      if (next) place(next);
    }
  };
  for (const top of topWords(words)) {
    if (options.showAll || top.weight >= 2 || chosen.has(top.id)) place(top);
  }
  return out;
}

/** Tap a word: pick it, or unpick it and whatever only it had revealed. Pick order is kept,
 *  because the follow-up questions are asked in the order the words were picked. */
export function toggle(words: readonly ConditionWordOut[], picked: readonly string[], id: string): string[] {
  if (!picked.includes(id)) return [...picked, id];
  let next = picked.filter((each) => each !== id);
  const byId = index(words);
  // Drop any picked word that is no longer showing: not a top word, and no picked word
  // still relates to it. Repeat, since dropping one can orphan its own reveals.
  for (;;) {
    const kept = next.filter((each) => {
      const word = byId.get(each);
      if (!word) return false;
      if (word.parent === null) return true;
      return next.some((other) => other !== each && byId.get(other)?.related.includes(each));
    });
    if (kept.length === next.length) return kept;
    next = kept;
  }
}

/** The words he picked that carry a follow-up question, in the order he picked them. */
export function asksFor(words: readonly ConditionWordOut[], picked: readonly string[]): ConditionWordOut[] {
  const byId = index(words);
  return picked.map((id) => byId.get(id)).filter((word): word is ConditionWordOut => Boolean(word?.ask));
}
