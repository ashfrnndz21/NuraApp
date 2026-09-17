import { describe, expect, it, vi } from "vitest";
import { Refused, Unreachable } from "../../src/api/client";
import { hold, replay, waiting, type Tap } from "../../src/offline/queue";
import { clearAllProfileData, clearProfileData } from "../../src/offline/todayCache";

/** Taps made offline (E00-08): held on the phone, sent once each, in the order he made them,
 *  when the network is back; a refusal is said; nothing outlives the region's midnight. */

const OWNER = { keyId: "owner", scopes: ["medicines", "records"] };
const SG = "Asia/Singapore";
const TEN_AM = new Date("2026-09-14T02:00:00Z"); // 10:00 in Singapore
let n = 0;
const profile = () => `p-${++n}`;
const taken = (id: string, lineId: string, at = TEN_AM.toISOString()): Tap => ({ id, kind: "taken", lineId, anchor: "breakfast", at });

describe("held taps", () => {
  it("are sent once each, oldest first, and then nothing is left to send", async () => {
    const id = profile();
    await hold(id, taken("t1", "line-a"), OWNER, TEN_AM, SG);
    await hold(id, taken("t2", "line-b"), OWNER, TEN_AM, SG);
    await hold(id, taken("t3", "line-c"), OWNER, TEN_AM, SG);
    const send = vi.fn(async (_tap: Tap) => ({}));
    const done = await replay(id, OWNER, TEN_AM, send);
    expect(send.mock.calls.map(([tap]) => tap.id)).toEqual(["t1", "t2", "t3"]);
    expect(done.sent.map((tap) => tap.id)).toEqual(["t1", "t2", "t3"]);
    expect(await waiting(id, OWNER, TEN_AM)).toEqual([]);
    await replay(id, OWNER, TEN_AM, send);
    expect(send).toHaveBeenCalledTimes(3);
  });

  it("stop at a lost network and keep the rest, in order, for next time", async () => {
    const id = profile();
    for (const each of ["t1", "t2", "t3"]) await hold(id, taken(each, `line-${each}`), OWNER, TEN_AM, SG);
    const send = vi.fn(async (tap: Tap) => {
      if (tap.id === "t2") throw new Unreachable();
      return {};
    });
    const done = await replay(id, OWNER, TEN_AM, send);
    expect(done).toMatchObject({ stopped: true, refused: [] });
    expect((await waiting(id, OWNER, TEN_AM)).map((tap) => tap.id)).toEqual(["t2", "t3"]);
  });

  it("stop at a server that could not answer, and keep the tap: the backend takes it twice as once", async () => {
    const id = profile();
    await hold(id, taken("t1", "line-a"), OWNER, TEN_AM, SG);
    const done = await replay(id, OWNER, TEN_AM, async () => Promise.reject(new Refused("HttpError", 503)));
    expect(done.stopped).toBe(true);
    expect((await waiting(id, OWNER, TEN_AM)).map((tap) => tap.id)).toEqual(["t1"]);
  });

  it("a refusal is reported in the backend's name for it, the tap is let go, and the rest still go", async () => {
    const id = profile();
    await hold(id, taken("t1", "line-gone"), OWNER, TEN_AM, SG);
    await hold(id, taken("t2", "line-b"), OWNER, TEN_AM, SG);
    const send = vi.fn(async (tap: Tap) => {
      if (tap.id === "t1") throw new Refused("NoSuchLine", 404);
      return {};
    });
    const done = await replay(id, OWNER, TEN_AM, send);
    expect(done.refused.map(({ tap, failure }) => [tap.id, failure.refusal])).toEqual([["t1", "NoSuchLine"]]);
    expect(done.sent.map((tap) => tap.id)).toEqual(["t2"]);
    expect(await waiting(id, OWNER, TEN_AM)).toEqual([]);
  });

  it("are replayed by one run at a time: two calls together send each tap once", async () => {
    const id = profile();
    await hold(id, taken("t1", "line-a"), OWNER, TEN_AM, SG);
    await hold(id, taken("t2", "line-b"), OWNER, TEN_AM, SG);
    const send = vi.fn(async () => new Promise((done) => setTimeout(done, 5)));
    const [first, second] = await Promise.all([replay(id, OWNER, TEN_AM, send), replay(id, OWNER, TEN_AM, send)]);
    expect(send).toHaveBeenCalledTimes(2);
    expect(first).toBe(second);
  });

  it("past the region's midnight are deleted, never sent: yesterday's tap is not today's tablet", async () => {
    const id = profile();
    await hold(id, taken("t1", "line-a"), OWNER, TEN_AM, SG);
    const nextMorning = new Date("2026-09-14T16:00:01Z"); // one second past midnight in Singapore
    const send = vi.fn(async () => ({}));
    expect(await replay(id, OWNER, nextMorning, send)).toMatchObject({ sent: [], refused: [] });
    expect(send).not.toHaveBeenCalled();
    expect(await waiting(id, OWNER, TEN_AM)).toEqual([]);
  });

  it("held under another key, or a narrower scope set, are deleted, never sent", async () => {
    const id = profile();
    await hold(id, taken("t1", "line-a"), OWNER, TEN_AM, SG);
    const narrower = { keyId: "owner", scopes: ["medicines"] };
    expect(await waiting(id, narrower, TEN_AM)).toEqual([]);
    expect(await waiting(id, OWNER, TEN_AM)).toEqual([]);
  });

  it("go with the rest of the phone's copy on a refusal, a switch of papers and sign-out", async () => {
    const one = profile();
    const two = profile();
    await hold(one, taken("t1", "line-a"), OWNER, TEN_AM, SG);
    await hold(two, taken("t2", "line-b"), OWNER, TEN_AM, SG);
    await clearProfileData(one);
    expect(await waiting(one, OWNER, TEN_AM)).toEqual([]);
    expect(await waiting(two, OWNER, TEN_AM)).toHaveLength(1);
    await clearAllProfileData();
    expect(await waiting(two, OWNER, TEN_AM)).toEqual([]);
  });

  it("never include a red feeling word: that is the moment to call, not to wait", async () => {
    const id = profile();
    const red: Tap = { id: "f1", kind: "feeling", word: "chest_pain", language: "en", at: TEN_AM.toISOString() };
    expect(await hold(id, red, OWNER, TEN_AM, SG, true)).toBeNull();
    const tired: Tap = { id: "f2", kind: "feeling", word: "tired", language: "en", at: TEN_AM.toISOString() };
    expect(await hold(id, tired, OWNER, TEN_AM, SG)).toEqual([tired]);
  });

  /** #171: a feeling tap without its own moment is refused, the same way a red word is —
   *  there would be nothing truer than "whenever the replay happens to run" to write it
   *  under, and that is exactly the wrong day a replay after midnight must never land on. */
  it("never include a feeling tap with no moment of its own", async () => {
    const id = profile();
    const noTime = { id: "f3", kind: "feeling", word: "tired", language: "en", at: "" } as Tap;
    expect(await hold(id, noTime, OWNER, TEN_AM, SG)).toBeNull();
    expect(await waiting(id, OWNER, TEN_AM)).toEqual([]);
  });

  /** #171: a feeling tap held offline is replayed like any other, and — the same rule as every
   *  tap in the queue — dropped rather than sent once it is past the midnight it was tapped
   *  on, so it never lands written under the wrong day. */
  it("a feeling tap, like Taken, is replayed with the word it carries, and dropped past its midnight rather than sent late", async () => {
    const id = profile();
    const felt: Tap = { id: "f4", kind: "feeling", word: "dizzy", language: "en", at: TEN_AM.toISOString() };
    await hold(id, felt, OWNER, TEN_AM, SG);
    const send = vi.fn(async (_tap: Tap) => ({}));
    expect((await replay(id, OWNER, TEN_AM, send)).sent).toEqual([felt]);
    expect(send).toHaveBeenCalledWith(felt);

    const id2 = profile();
    await hold(id2, { ...felt, id: "f5" }, OWNER, TEN_AM, SG);
    const nextMorning = new Date("2026-09-14T16:00:01Z"); // one second past midnight in Singapore
    const lateSend = vi.fn(async () => ({}));
    expect(await replay(id2, OWNER, nextMorning, lateSend)).toMatchObject({ sent: [], refused: [] });
    expect(lateSend).not.toHaveBeenCalled();
  });
});
