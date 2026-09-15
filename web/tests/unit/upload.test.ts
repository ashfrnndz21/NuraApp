import { describe, expect, it } from "vitest";
import type { ConsultOut, UploadOut } from "../../src/api/types";
import { ChunkedUpload, FIRST_AT_LEAST, NoConnection, type UploadCalls, type UploadDeps } from "../../src/visit/upload";

/** The network did not answer. */
class Dropped extends Error {}
/** The server said no, by the refusal's name. */
class No extends Error {
  constructor(readonly refusal: string) {
    super(refusal);
  }
}

const KEPT = { recording: { recording_id: "r1" }, summary: null, summary_refused: null } as unknown as ConsultOut;

/** A server that keeps chunks the way `app.ingestion.chunks` does — in order, once each — and
 *  a network that can drop, before the server hears a call or after, when only its answer is
 *  lost. */
function server() {
  const net = { down: false, loseNextAnswer: false };
  const s = { id: 0, upload: "", chunks: [] as Uint8Array[], yes: false, open: true, finished: false };
  const log: string[] = [];
  const discarded: string[] = [];
  let opening: (() => void) | null = null;
  const out = (): UploadOut => ({
    upload_id: s.upload,
    chunks: s.chunks.length,
    received_bytes: s.chunks.reduce((sum, one) => sum + one.length, 0),
    doctor_said_yes: s.yes,
    open: s.open,
    max_chunk_bytes: 1024,
  });
  const reach = async <T>(what: string, work: () => T): Promise<T> => {
    log.push(what);
    if (net.down) throw new Dropped();
    const answer = work();
    if (net.loseNextAnswer) {
      net.loseNextAnswer = false;
      throw new Dropped();
    }
    return answer;
  };
  const calls: UploadCalls = {
    open: async () => {
      if (opening === null && holdOpen.hold) await new Promise<void>((done) => (opening = done));
      return reach("open", () => {
        s.id += 1;
        Object.assign(s, { upload: `u${s.id}`, chunks: [], yes: false, open: true });
        return out();
      });
    },
    status: () => reach("status", out),
    chunk: async (upload, position, bytes) => {
      const data = new Uint8Array(await bytes.arrayBuffer());
      return reach(`chunk ${position}`, () => {
        if (upload !== s.upload || !s.open) throw new No("UploadClosed");
        if (position !== s.chunks.length) throw new No("ChunkOutOfOrder");
        s.chunks.push(data);
        return out();
      });
    },
    yes: () => reach("yes", () => ((s.yes = true), out())),
    finish: () =>
      reach("finish", () => {
        if (!s.yes) throw new No("NoYesFromTheDoctor");
        s.finished = true;
        return KEPT;
      }),
    discard: (upload, because) => void discarded.push(`${upload} ${because}`),
  };
  const holdOpen = { hold: false, release: () => opening?.() };
  const ticks: (() => void)[] = [];
  const onlines: (() => void)[] = [];
  const deps: UploadDeps = {
    calls,
    every: (_ms, tick) => {
      ticks.push(tick);
      return () => void ticks.splice(ticks.indexOf(tick), 1);
    },
    onOnline: (back) => {
      onlines.push(back);
      return () => void onlines.splice(onlines.indexOf(back), 1);
    },
    unreachable: (failure) => failure instanceof Dropped,
    refusal: (failure) => (failure instanceof No ? failure.refusal : null),
  };
  const bytes = () => {
    const all = new Uint8Array(s.chunks.reduce((sum, one) => sum + one.length, 0));
    let at = 0;
    for (const one of s.chunks) {
      all.set(one, at);
      at += one.length;
    }
    return all;
  };
  return { deps, net, s, log, discarded, holdOpen, ticks, onlines, bytes };
}

const audio = (text: string) => new Blob([new TextEncoder().encode(text)], { type: "audio/webm" });
const decoded = (data: Uint8Array) => new TextDecoder().decode(data);
const settle = () => new Promise((done) => setTimeout(done, 0));

function upload(deps: UploadDeps) {
  return new ChunkedUpload(deps, "audio/webm;codecs=opus", "2026-09-14T02:30:00.000Z");
}

describe("a recording sent in chunks as it is made (#129)", () => {
  it("sends what the server does not have yet, in order, as it records", async () => {
    const at = server();
    const one = upload(at.deps);
    one.start();
    one.add(audio("the notice and his yes."));
    await one.send();
    one.add(audio(" the visit."));
    at.ticks[0]!();
    await one.send();
    expect(at.log).toEqual(["open", "chunk 0", "chunk 1"]);
    expect(decoded(at.bytes())).toBe("the notice and his yes. the visit.");
    expect(one.sent).toBe(one.recorded);
  });

  it("after a dropped connection asks the server how far it got, and goes on from there", async () => {
    const at = server();
    const one = upload(at.deps);
    one.start();
    one.add(audio("0123456789abcdef"));
    await one.send();
    // The signal goes: nothing reaches the server, and the phone says so.
    at.net.down = true;
    one.add(audio("-while-away"));
    await one.send();
    expect(one.connected.value).toBe(false);
    // Back: the online event sends from where the server says it got to.
    at.net.down = false;
    at.onlines[0]!();
    await one.send();
    expect(one.connected.value).toBe(true);
    expect(at.log.slice(-2)).toEqual(["status", "chunk 1"]);
    // The server kept a chunk but its answer was lost: nothing is sent twice.
    at.net.loseNextAnswer = true;
    one.add(audio("-kept-but-unheard"));
    await one.send();
    one.add(audio("-last"));
    await one.send();
    expect(decoded(at.bytes())).toBe("0123456789abcdef-while-away-kept-but-unheard-last");
  });

  it("waits with the first chunk until it holds the container's header, or Stop", async () => {
    const at = server();
    const one = upload(at.deps);
    one.start();
    one.add(audio("x".repeat(FIRST_AT_LEAST - 1)));
    await one.send();
    expect(at.log).toEqual(["open"]);
    await one.doctorSaidYes();
    await one.finish(2);
    expect(at.log).toEqual(["open", "yes", "chunk 0", "finish"]);
  });

  it("Stop sends the doctor's yes and the rest, then asks the server to put it together", async () => {
    const at = server();
    const one = upload(at.deps);
    one.start();
    one.add(audio("the notice, then his answer"));
    await one.doctorSaidYes();
    one.add(audio(", then the visit"));
    expect(await one.finish(66)).toBe(KEPT);
    expect(at.s.finished).toBe(true);
    expect(decoded(at.bytes())).toBe("the notice, then his answer, then the visit");
    expect(at.ticks).toEqual([]); // it sends nothing more after
    one.add(audio("late"));
    await one.send();
    expect(at.log.filter((call) => call.startsWith("chunk"))).toHaveLength(2);
  });

  it("Stop with no connection says so, and Stop again once it is back keeps it", async () => {
    const at = server();
    const one = upload(at.deps);
    one.start();
    one.add(audio("the whole visit, heard"));
    await one.doctorSaidYes();
    at.net.down = true;
    one.add(audio(" to the end"));
    await expect(one.finish(66)).rejects.toBeInstanceOf(NoConnection);
    at.net.down = false;
    expect(await one.finish(66)).toBe(KEPT);
    expect(decoded(at.bytes())).toBe("the whole visit, heard to the end");
  });

  it("a no throws it away on the server too, even with the open still on its way", async () => {
    const at = server();
    at.holdOpen.hold = true;
    const one = upload(at.deps);
    one.start();
    one.add(audio("the notice and his no"));
    one.discard("no");
    at.holdOpen.release();
    await settle();
    await settle();
    expect(at.discarded).toEqual(["u1 no"]);
    one.add(audio("after"));
    await one.send();
    expect(at.log.filter((call) => call.startsWith("chunk"))).toEqual([]);
  });

  it("an upload the server closed is opened again and sent from the start, with the yes", async () => {
    const at = server();
    const one = upload(at.deps);
    one.start();
    one.add(audio("the notice, his yes"));
    await one.doctorSaidYes();
    // The server let it lapse while the phone was away.
    at.s.open = false;
    one.add(audio(", the visit"));
    await one.send();
    expect(at.s.upload).toBe("u2");
    expect(at.s.yes).toBe(true);
    expect(decoded(at.bytes())).toBe("the notice, his yes, the visit");
  });
});
