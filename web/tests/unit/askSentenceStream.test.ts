import { afterEach, describe, expect, it, vi } from "vitest";
import { askStream } from "../../src/api/nura";

/** Ask's answer streams sentence by sentence (P1, docs/design-direction.md "the answer streams
 *  sentence by sentence"): `Ask.tsx` appends one sentence, text and cites, the instant its own
 *  `answer_sentence` event arrives — no fake typewriter timing, no held-back reveal. Both
 *  askers send the same contract: `ClaudeAsker` streams its own already-checked lines,
 *  `RuleBasedAsker` replays `recall_stream`'s own already-composed ones (`app.search.asker`),
 *  so the web client (and this test) never special-cases which one answered. */

afterEach(() => {
  vi.unstubAllGlobals();
});

function sseResponse(events: readonly Record<string, unknown>[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function stub(response: Response): void {
  vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8124" } });
  vi.stubGlobal("fetch", vi.fn(async () => response));
}

describe("askStream: answer_sentence events land as their own sentences, before the answer", () => {
  it("hands two answer_sentence events to onSentence, in order with their cites, before the final answer resolves", async () => {
    stub(
      sseResponse([
        { type: "step", key: "medicines", label: "Checking your medicines.", name: "medicines" },
        { type: "answer_sentence", text: "Amlodipine 5mg is on your list.", cites: [{ kind: "medication_line", id: "m1" }] },
        { type: "answer_sentence", text: "It was started on 1 August.", cites: [{ kind: "fact", id: "f1" }] },
        {
          type: "answer",
          answer: {
            question_artifact_id: "q1",
            mode: "text",
            language: "en",
            answered: true,
            lines: [
              { text: "Amlodipine 5mg is on your list.", cites: [{ kind: "medication_line", id: "m1" }] },
              { text: "It was started on 1 August.", cites: [{ kind: "fact", id: "f1" }] },
            ],
            honest: [],
            boundary: ["Nura does not decide what is wrong."],
            spoken: [],
            withheld: [],
            looked_at: [{ kind: "medicines", label: "medicines" }],
          },
        },
      ]),
    );

    const seenBeforeAnswer: { text: string; cites: unknown }[] = [];
    let lengthWhenLastSentenceLanded = 0;
    const answer = await askStream(
      "token",
      "profile-1",
      "what is my medicine",
      "text",
      "en",
      () => undefined,
      (text, cites) => {
        seenBeforeAnswer.push({ text, cites });
        lengthWhenLastSentenceLanded = seenBeforeAnswer.length;
      },
    );

    expect(seenBeforeAnswer.map((s) => s.text)).toEqual(["Amlodipine 5mg is on your list.", "It was started on 1 August."]);
    expect(seenBeforeAnswer[0]!.cites).toEqual([{ kind: "medication_line", id: "m1" }]);
    // Both sentences landed before the stream's own final `answer` event — resolving this
    // promise — was even processed: nothing here waited for the whole answer.
    expect(lengthWhenLastSentenceLanded).toBe(2);
    expect(answer.boundary).toEqual(["Nura does not decide what is wrong."]);
    expect(answer.looked_at).toEqual([{ kind: "medicines", label: "medicines" }]);
  });

  it("the rule-based asker's answer also streams one answer_sentence per line, matching the final answer's own lines", async () => {
    stub(
      sseResponse([
        { type: "step", key: "medicines", label: "Checking your medicines.", name: "medicines" },
        { type: "answer_sentence", text: "Amlodipine 5mg is on your list.", cites: [{ kind: "medication_line", id: "m1" }] },
        {
          type: "answer",
          answer: {
            question_artifact_id: "q1",
            mode: "text",
            language: "en",
            answered: true,
            lines: [{ text: "Amlodipine 5mg is on your list.", cites: [{ kind: "medication_line", id: "m1" }] }],
            honest: [],
            boundary: ["Nura does not decide what is wrong."],
            spoken: [],
            withheld: [],
          },
        },
      ]),
    );
    const sentences: string[] = [];
    const answer = await askStream("token", "profile-1", "what is my medicine", "text", "en", () => undefined, (text) => sentences.push(text));
    expect(sentences).toEqual(answer.lines.map((line) => line.text));
  });
});
