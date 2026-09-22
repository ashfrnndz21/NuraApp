import { afterEach, describe, expect, it, vi } from "vitest";
import { apiStream, Refused, STREAM_IDLE_MS, Unreachable } from "../../src/api/client";

/** The ask bar and the feed's web/video search stream over `apiStream` (docs/design-
 *  direction.md "Conversation, waiting and thinking"). The honesty rule tested here at the
 *  wire: a real event is handed to the caller the moment it arrives — no buffering, no
 *  artificial delay — and a stream that stalls still ends in a plain `Unreachable` within
 *  `STREAM_IDLE_MS`, never spinning for ever (#193).
 */

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function sseResponse(events: readonly Record<string, unknown>[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function stub(response: Response | (() => Promise<Response>)): ReturnType<typeof vi.fn> {
  vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8124" } });
  const fetchMock = vi.fn(typeof response === "function" ? response : async () => response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("apiStream: events arrive as they are given, in order, with no delay", () => {
  it("hands every event to the caller in the order the backend sent them", async () => {
    stub(
      sseResponse([
        { type: "step", key: "medicines" },
        { type: "step", key: "visits" },
        { type: "answer", answer: { lines: [] } },
      ]),
    );
    const seen: unknown[] = [];
    await apiStream("/profiles/p/ask/stream", { method: "POST", body: {} }, (event) => seen.push(event));
    expect(seen).toEqual([
      { type: "step", key: "medicines" },
      { type: "step", key: "visits" },
      { type: "answer", answer: { lines: [] } },
    ]);
  });

  it("resolves the instant the stream ends — nothing here holds a fast answer back to look slower", async () => {
    const started = Date.now();
    stub(sseResponse([{ type: "answer", answer: { lines: [] } }]));
    await apiStream("/profiles/p/ask/stream", { method: "POST", body: {} }, () => undefined);
    // A real 200ms answer must not become a padded one: there is no timer in `apiStream` that
    // could add latency, only the idle-timeout that only ever fires on silence.
    expect(Date.now() - started).toBeLessThan(200);
  });

  it("throws Refused for a refusal event, the same shape a plain call throws it", async () => {
    stub(sseResponse([{ type: "refusal", refusal: "OutOfScope", status: 403, scope: "medicines" }]));
    const failure = await apiStream("/profiles/p/ask/stream", { method: "POST", body: {} }, () => undefined).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(Refused);
    expect(failure).toMatchObject({ refusal: "OutOfScope", status: 403, scope: "medicines" });
  });
});

describe("apiStream: a stalled stream ends in a plain failure within the deadline (#193)", () => {
  it("aborts and rejects with Unreachable when nothing arrives, ever", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8124" } });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string | URL, init: RequestInit = {}) => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            // The real thing this stands in for: a connection that opens, sends nothing, and
            // is never closed by the far end — `apiStream`'s idle timeout is what ends it, by
            // aborting the signal it gave `fetch`, which the real Fetch spec wires straight
            // into the body stream erroring out; reproduced here since the mock has no real
            // network underneath it to do that wiring on its own.
            init.signal?.addEventListener("abort", () => controller.error(new DOMException("aborted", "AbortError")));
          },
        });
        return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }),
    );

    const call = apiStream("/profiles/p/ask/stream", { method: "POST", body: {} }, () => undefined);
    const settled = call.then(
      () => "resolved",
      (failure: unknown) => failure,
    );
    await vi.advanceTimersByTimeAsync(STREAM_IDLE_MS + 1000);
    await expect(settled).resolves.toBeInstanceOf(Unreachable);
  });
});
