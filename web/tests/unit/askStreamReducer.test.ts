import { describe, expect, it } from "vitest";
import { appendSentence, shownSentences } from "../../src/feed/askStream";

describe("askStream: the sentence-by-sentence reducer Ask.tsx renders from", () => {
  it("appends sentences in order, never reordering or dropping one", () => {
    let sentences = appendSentence([], "Your last blood test was on 21 January 2025.", []);
    sentences = appendSentence(sentences, "There is no newer one in your papers.", []);
    expect(sentences.map((s) => s.text)).toEqual(["Your last blood test was on 21 January 2025.", "There is no newer one in your papers."]);
  });

  it("keeps each sentence's own cites, unchanged, alongside its text", () => {
    const cites = [{ kind: "fact", id: "f1" }];
    const sentences = appendSentence([], "Your last blood test was on 21 January 2025.", cites);
    expect(sentences[0]!.cites).toBe(cites);
  });

  it("shownSentences shows the streamed list while nothing final has arrived", () => {
    const streamed = appendSentence([], "First.", []);
    expect(shownSentences(streamed, null)).toBe(streamed);
  });

  it("shownSentences shows only the finished answer's own lines once they arrive — never the streamed list too, so nothing duplicates", () => {
    const streamed = appendSentence(appendSentence([], "First.", []), "Second.", []);
    const final = [
      { text: "First.", cites: [], clip: null },
      { text: "Second.", cites: [], clip: null },
    ];
    const shown = shownSentences(streamed, final);
    expect(shown).toBe(final);
    expect(shown).not.toBe(streamed);
    // The finished answer's own two lines, not four — streamed and final are never concatenated.
    expect(shown).toHaveLength(2);
  });

  it("an empty final answer (the honest 'not written down' path) shows nothing here — 'honest' is its own field, never folded into the sentence list", () => {
    expect(shownSentences([], [])).toEqual([]);
  });
});
