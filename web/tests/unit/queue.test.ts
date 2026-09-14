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
});
