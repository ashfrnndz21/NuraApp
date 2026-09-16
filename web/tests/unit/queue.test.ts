import { afterEach, describe, expect, it, vi } from "vitest";

/** The client's one queue (W7): calls go one at a time, and an urgent one — a red word, the
 *  not-feeling-well button — goes next, ahead of every call still waiting, and ahead too of a
 *  background read already on the wire when it is made (that read is aborted to make room; see
 *  `api/client.ts`). A write already on the wire cannot be taken back once the backend may have
 *  seen it, so it is left to finish, and the urgent call is sent the moment it clears — never
 *  later than that. This is the regression for CI run 35065730744: a red word said while
 *  Today's own feed read (#165) was still on the wire used to lose that race. */

function fetchThatGates() {
  const started: string[] = [];
  const aborted: string[] = [];
  const gates = new Map<string, () => void>();
  vi.stubGlobal("window", { location: { origin: "http://127.0.0.1" } });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: URL, init: RequestInit) => {
      const path = new URL(url).pathname;
      started.push(path);
      return new Promise<Response>((done, fail) => {
        gates.set(path, () => done(new Response("{}", { status: 200 })));
        init.signal?.addEventListener("abort", () => {
          aborted.push(path);
          fail(new DOMException("aborted", "AbortError"));
        });
      });
    }),
  );
  return { started, aborted, gates };
}

describe("the queue", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("aborts a background read already on the wire for an urgent call, sends the urgent call in its place, and only then the reads that were still waiting", async () => {
    const { started, aborted, gates } = fetchThatGates();
    const { api, Unreachable } = await import("../../src/api/client");
    const settle = () => new Promise((done) => setTimeout(done, 0));
    // One call at a time is dispatched; the rest sit in `waiting` until it clears.
    const state = api("/profiles/p/state").catch((failure: unknown) => failure);
    const medicines = api("/profiles/p/medicines");
    const feed = api("/profiles/p/feed");
    await settle();
    expect(started).toEqual(["/api/profiles/p/state"]);
    const red = api("/profiles/p/feelings", { method: "POST", body: { word: "chest_tightness" }, urgent: true });
    await settle();
    // The read on the wire is cut short, not waited on: the urgent call takes its place at
    // once, and the caller it interrupted sees exactly what a lost network looks like.
    expect(aborted).toEqual(["/api/profiles/p/state"]);
    expect(started).toEqual(["/api/profiles/p/state", "/api/profiles/p/feelings"]);
    expect(await state).toBeInstanceOf(Unreachable);
    // Each read that was only ever waiting follows, in the order it was queued.
    gates.get("/api/profiles/p/feelings")!();
    await settle();
    await red;
    expect(started).toEqual(["/api/profiles/p/state", "/api/profiles/p/feelings", "/api/profiles/p/medicines"]);
    gates.get("/api/profiles/p/medicines")!();
    await settle();
    expect(started).toEqual(["/api/profiles/p/state", "/api/profiles/p/feelings", "/api/profiles/p/medicines", "/api/profiles/p/feed"]);
    gates.get("/api/profiles/p/feed")!();
    await Promise.all([medicines, feed]);
  });

  it("leaves a write already on the wire to finish, and sends the urgent call the moment it clears — still ahead of a read only waiting", async () => {
    const { started, gates } = fetchThatGates();
    const { api } = await import("../../src/api/client");
    const settle = () => new Promise((done) => setTimeout(done, 0));
    const taken = api("/profiles/p/medicines/l1/taken", { method: "POST", body: { anchor: "am" } });
    const medicines = api("/profiles/p/medicines");
    await settle();
    expect(started).toEqual(["/api/profiles/p/medicines/l1/taken"]);
    const red = api("/profiles/p/feelings", { method: "POST", body: { word: "chest_tightness" }, urgent: true });
    await settle();
    // A write already sending is not interrupted: the backend may already have it, and taking
    // it back is not this queue's to decide.
    expect(started).toEqual(["/api/profiles/p/medicines/l1/taken"]);
    gates.get("/api/profiles/p/medicines/l1/taken")!();
    await settle();
    await taken;
    // The moment it clears, the urgent call is next — before the read that was only waiting.
    expect(started).toEqual(["/api/profiles/p/medicines/l1/taken", "/api/profiles/p/feelings"]);
    gates.get("/api/profiles/p/feelings")!();
    await settle();
    await red;
    expect(started).toEqual(["/api/profiles/p/medicines/l1/taken", "/api/profiles/p/feelings", "/api/profiles/p/medicines"]);
    gates.get("/api/profiles/p/medicines")!();
    await medicines;
  });

  it("gives an urgent call up as unreachable at its deadline when a write stuck on the wire will not clear, and never sends it late", async () => {
    vi.useFakeTimers();
    const started: string[] = [];
    const aborted: string[] = [];
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1" } });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: URL, init: RequestInit) => {
        const path = new URL(url).pathname;
        started.push(path);
        // Nothing ever answers: the connection is up, the server is not — and a write is
        // never aborted to make room, so the urgent call queued behind it can only wait.
        return new Promise<Response>((_done, fail) =>
          init.signal?.addEventListener("abort", () => {
            aborted.push(path);
            fail(new DOMException("aborted", "AbortError"));
          }),
        );
      }),
    );
    const { api, CALL_DEADLINE_MS, Unreachable, URGENT_DEADLINE_MS } = await import("../../src/api/client");
    const stuck = api("/profiles/p/medicines/l1/taken", { method: "POST", body: { anchor: "am" } }).catch((failure: unknown) => failure);
    await vi.advanceTimersByTimeAsync(0);
    const red = api("/profiles/p/feelings", { method: "POST", body: { word: "chest_tightness" }, urgent: true }).catch((failure: unknown) => failure);
    await vi.advanceTimersByTimeAsync(URGENT_DEADLINE_MS);
    expect(await red).toBeInstanceOf(Unreachable);
    expect(started).toEqual(["/api/profiles/p/medicines/l1/taken"]);
    // The stuck write gives up too, on its own longer deadline, well after the red word it
    // held back has already been given up on.
    await vi.advanceTimersByTimeAsync(CALL_DEADLINE_MS);
    expect(await stuck).toBeInstanceOf(Unreachable);
    expect(aborted).toEqual(["/api/profiles/p/medicines/l1/taken"]);
    expect(started).toEqual(["/api/profiles/p/medicines/l1/taken"]);

    // An urgent call that is itself on the wire, with nothing ahead of it to abort, is given
    // up on at its own deadline the same way.
    const alone = api("/profiles/p/not-feeling-well", { method: "POST", body: { words: "chest pain" }, urgent: true }).catch((failure: unknown) => failure);
    await vi.advanceTimersByTimeAsync(0);
    expect(started.at(-1)).toBe("/api/profiles/p/not-feeling-well");
    await vi.advanceTimersByTimeAsync(URGENT_DEADLINE_MS);
    expect(await alone).toBeInstanceOf(Unreachable);
    expect(aborted).toContain("/api/profiles/p/not-feeling-well");
    vi.useRealTimers();
  });
});
