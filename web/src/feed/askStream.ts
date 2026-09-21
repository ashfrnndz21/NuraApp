import type { AnswerLineOut } from "../api/types";

/** One sentence of Ask's answer as it streams in (P1, `answer_sentence` — `app.search.asker.
 *  AnswerDelta`, `app.channels.api.timeline._stream_turn`): the text, already past the
 *  plain-words gate, and the exact cites it rests on. Sent by both askers, in order, before
 *  the final `answer` event — `web/src/screens/Ask.tsx` never has to know which one answered. */
export interface StreamedSentence {
  text: string;
  cites: AnswerLineOut["cites"];
}

/** Append one sentence (append-only: a sentence already shown is never edited or reordered).
 *  `SoftText` itself never replays an already-shown word (docs/design/experience-blueprint.html
 *  `stream()`; `web/src/ui/kit/SoftText.tsx`) as long as a sentence already on screen keeps
 *  rendering the same text on every re-render — which appending, never mutating in place,
 *  guarantees. */
export function appendSentence(sentences: readonly StreamedSentence[], text: string, cites: AnswerLineOut["cites"]): StreamedSentence[] {
  return [...sentences, { text, cites }];
}

/** What the growing answer shows, right now: the finished answer's own lines once they have
 *  arrived (`final`, authoritative — cites, a clip, everything `AnswerOut` carries) — otherwise
 *  the sentences streamed so far. Never both: this is a replacement, not an append, so a
 *  sentence already shown while streaming is never shown a second time once the final `answer`
 *  event lands and `final` stops being `null`. */
export function shownSentences<S, F>(streamed: readonly S[], final: readonly F[] | null): readonly S[] | readonly F[] {
  return final ?? streamed;
}
