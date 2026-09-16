import { afterEach, describe, expect, it, vi } from "vitest";
import { api, Refused, Unreachable } from "../../src/api/client";

/** A "no" is always a refusal the screen can say, whatever the body it came in. */

afterEach(() => vi.unstubAllGlobals());

function answering(status: number, body: string, type = "text/plain") {
  vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8124" } });
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status, headers: { "Content-Type": type } })));
}

describe("a refusal", () => {
  it("is the backend's refusal by its name when the body carries one", async () => {
    answering(413, JSON.stringify({ refusal: "PhotoTooLarge" }), "application/json");
    await expect(api("/profiles/p/photos", { method: "POST", body: {} })).rejects.toMatchObject({ refusal: "PhotoTooLarge", status: 413 });
  });

  it("is TooLarge when a layer in front of the app answers 413 with a page that is not JSON", async () => {
    answering(413, "<html><body>Request Entity Too Large</body></html>", "text/html");
    const failure = await api("/profiles/p/photos", { method: "POST", body: {} }).catch((each: unknown) => each);
    expect(failure).toBeInstanceOf(Refused);
    expect(failure).toMatchObject({ refusal: "TooLarge", status: 413 });
  });

  it("is HttpError for any other bare no, and never a crash on the body", async () => {
    answering(502, "Bad Gateway");
    await expect(api("/me")).rejects.toMatchObject({ refusal: "HttpError", status: 502 });
  });
});

/** The mechanism behind #191, tested at the queue itself rather than through a browser and a
 *  clock: a red word must not sit behind a background read, whatever that read's own timing
 *  happens to be. `fetch` here is a background read that never resolves on its own — only an
 *  abort ends it — so if `enqueue` ever failed to cut the urgent call in and abort what was on
 *  the wire, this test would hang (and Vitest's own test timeout would fail it), not merely
 *  read a fragile "which request started first" off the wire the way the e2e trail does. */
describe("the urgent queue (#191): a red word cuts ahead of a background read", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("aborts a non-urgent, already-on-the-wire read and sends the urgent call immediately, not once the read finishes", async () => {
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:8124" } });
    const order: string[] = [];
    let readSignal: AbortSignal | undefined;

    const fetchMock = vi.fn((url: string | URL, init: RequestInit = {}) => {
      const path = new URL(url).pathname;
      if (path === "/api/profiles/p/feed") {
        order.push("read:start");
        readSignal = init.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          // Never resolves by itself: the only way out is the queue aborting it for the
          // urgent call. If that stops happening, this promise — and the test — hangs.
          readSignal?.addEventListener("abort", () => {
            order.push("read:aborted");
            reject(new DOMException("aborted", "AbortError"));
          });
        });
      }
      if (path === "/api/profiles/p/not-feeling-well") {
        order.push("urgent:start");
        return Promise.resolve(new Response(JSON.stringify({ kind: "red_flag" }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      throw new Error(`unexpected fetch in this test: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    // A background read, genuinely on the wire (its fetch has actually been called) — the
    // shape of a page's own refresh, or the emergency card kept for offline (#213, #194).
    const read = api("/profiles/p/feed");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(order).toEqual(["read:start"]);

    // The red word, said while that read is still open.
    const urgent = api("/profiles/p/not-feeling-well", { method: "POST", urgent: true });

    await expect(urgent).resolves.toMatchObject({ kind: "red_flag" });
    await expect(read).rejects.toBeInstanceOf(Unreachable);
    // The abort happens, and the urgent call is sent — never the read finishing on its own
    // first, because it never finishes on its own at all in this test.
    expect(order).toEqual(["read:start", "read:aborted", "urgent:start"]);
  });
});
