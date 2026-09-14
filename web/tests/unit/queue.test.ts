import { afterEach, describe, expect, it, vi } from "vitest";

/** The client's one queue (W7): calls go one at a time, and an urgent one — a red word, the
 *  not-feeling-well button — goes next, ahead of every call still waiting. */

describe("the queue", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends an urgent call next, behind only the call already on the wire", async () => {
    const started: string[] = [];
    const gates: (() => void)[] = [];
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1" } });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: URL) => {
        started.push(new URL(url).pathname);
        return new Promise<Response>((done) => gates.push(() => done(new Response("{}", { status: 200 }))));
      }),
    );
    const { api } = await import("../../src/api/client");
    const settle = () => new Promise((done) => setTimeout(done, 0));
    const calls = [api("/profiles/p/state"), api("/profiles/p/medicines"), api("/profiles/p/feed")];
    await settle();
    expect(started).toEqual(["/api/profiles/p/state"]);
    const red = api("/profiles/p/feelings", { method: "POST", body: { word: "chest_tightness" }, urgent: true });
    for (let i = 0; i < 4; i += 1) {
      gates.shift()?.();
      await settle();
    }
    await Promise.all([...calls, red]);
    expect(started).toEqual(["/api/profiles/p/state", "/api/profiles/p/feelings", "/api/profiles/p/medicines", "/api/profiles/p/feed"]);
  });

  it("gives an urgent call up as unreachable at its deadline, whatever is stuck on the wire, and never sends it later", async () => {
    vi.useFakeTimers();
    const started: string[] = [];
    const aborted: string[] = [];
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1" } });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: URL, init: RequestInit) => {
        const path = new URL(url).pathname;
        started.push(path);
        // Nothing ever answers: the connection is up, the server is not.
        return new Promise<Response>((_done, fail) =>
          init.signal?.addEventListener("abort", () => {
            aborted.push(path);
            fail(new DOMException("aborted", "AbortError"));
          }),
        );
      }),
    );
    const { api, CALL_DEADLINE_MS, Unreachable, URGENT_DEADLINE_MS } = await import("../../src/api/client");
    const stuck = api("/profiles/p/feed").catch((failure: unknown) => failure);
    await vi.advanceTimersByTimeAsync(0);
    const red = api("/profiles/p/feelings", { method: "POST", body: { word: "chest_tightness" }, urgent: true }).catch((failure: unknown) => failure);
    await vi.advanceTimersByTimeAsync(URGENT_DEADLINE_MS);
    expect(await red).toBeInstanceOf(Unreachable);
    expect(started).toEqual(["/api/profiles/p/feed"]);
    // The stuck read gives up too, and the red word it held back is not sent after all.
    await vi.advanceTimersByTimeAsync(CALL_DEADLINE_MS);
    expect(await stuck).toBeInstanceOf(Unreachable);
    expect(aborted).toEqual(["/api/profiles/p/feed"]);
    expect(started).toEqual(["/api/profiles/p/feed"]);

    // An urgent call that is itself on the wire is aborted at its deadline.
    const alone = api("/profiles/p/not-feeling-well", { method: "POST", body: { words: "chest pain" }, urgent: true }).catch((failure: unknown) => failure);
    await vi.advanceTimersByTimeAsync(0);
    expect(started.at(-1)).toBe("/api/profiles/p/not-feeling-well");
    await vi.advanceTimersByTimeAsync(URGENT_DEADLINE_MS);
    expect(await alone).toBeInstanceOf(Unreachable);
    expect(aborted).toContain("/api/profiles/p/not-feeling-well");
    vi.useRealTimers();
  });
});
