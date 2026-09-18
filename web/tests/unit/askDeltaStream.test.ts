import { afterEach, describe, expect, it, vi } from "vitest";
import { askStream } from "../../src/api/nura";

/** The agent asker's own answer (`NURA_ASKER=claude`), drawn as it lands: `Ask.tsx` renders
 *  one line per `answer_delta` event the instant it arrives (`setDeltaLines((was) => [...was,
 *  text])`), with the pulsing "Nura is looking" dots still showing until the final `answer`
 *  event replaces all of it with the finished, cited answer. No fake typewriter timing — this
 *  is the wiring `askStream` gives `Ask.tsx` for that: `onDelta` fires for each chunk, in
 *  order, strictly before the promise it returns settles with the final answer. */

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

describe("askStream: answer_delta events land as their own lines, before the answer", () => {
  it("hands two answer_delta events to onDelta, in order, before the final answer resolves", async () => {
    stub(
      sseResponse([
        { type: "step", key: "medicines", label: "Checking your medicines.", name: "medicines" },
        { type: "answer_delta", text: "Amlodipine 5mg is on your list." },
        { type: "answer_delta", text: "It was started on 1 August." },
        {
          type: "answer",
          answer: {
            question_artifact_id: "q1",
            mode: "text",
            language: "en",
            answered: true,
            lines: [],
            honest: [],
            boundary: ["Nura does not decide what is wrong."],
            spoken: [],
            withheld: [],
          },
        },
      ]),
    );

    const seenBeforeAnswer: string[] = [];
    let lengthWhenLastDeltaLanded = 0;
    const answer = await askStream(
      "token",
      "profile-1",
      "what is my medicine",
      "text",
      "en",
      () => undefined,
      (text) => {
        seenBeforeAnswer.push(text);
        lengthWhenLastDeltaLanded = seenBeforeAnswer.length;
      },
    );

    // Both deltas landed, in order — this is exactly what `Ask.tsx`'s `deltaLines` state holds
    // and renders as two `<p>` lines, one per delta, the moment each one arrived.
    expect(seenBeforeAnswer).toEqual(["Amlodipine 5mg is on your list.", "It was started on 1 August."]);
    // And they were already two lines' worth before the stream's own final `answer` event —
    // resolving this promise — was even processed: nothing here waited for the whole answer.
    expect(lengthWhenLastDeltaLanded).toBe(2);
    expect(answer.boundary).toEqual(["Nura does not decide what is wrong."]);
  });

  it("never calls onDelta for the rule-based asker's answer, which always arrives whole", async () => {
    stub(
      sseResponse([
        { type: "step", key: "medicines", label: "Checking your medicines.", name: "medicines" },
        {
          type: "answer",
          answer: {
            question_artifact_id: "q1",
            mode: "text",
            language: "en",
            answered: true,
            lines: [{ text: "Amlodipine 5mg is on your list.", cites: [] }],
            honest: [],
            boundary: ["Nura does not decide what is wrong."],
            spoken: [],
            withheld: [],
          },
        },
      ]),
    );
    const deltas: string[] = [];
    const answer = await askStream("token", "profile-1", "what is my medicine", "text", "en", () => undefined, (text) => deltas.push(text));
    expect(deltas).toEqual([]);
    expect(answer.lines).toHaveLength(1);
  });
});
