import { describe, expect, it, vi } from "vitest";
import { ConsultRecorder, pickMimeType, type RecorderDeps, type RecorderLike } from "../../src/visit/recorder";

/** A stand-in MediaRecorder: it records what the page does with it, and hands back the chunks
 *  it was given when it stops. */
function fake(types: string[] = ["audio/webm;codecs=opus"]) {
  let now = 1_000;
  const ticks: (() => void)[] = [];
  const made: (RecorderLike & { started: number; stopped: number; feed(data: string): void })[] = [];
  const tracks = { stopped: 0 };
  const locks = { taken: 0, released: 0 };
  const deps: RecorderDeps = {
    getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: () => void (tracks.stopped += 1) }] })),
    makeRecorder: (_stream, mimeType) => {
      const recorder = {
        state: "inactive" as RecorderLike["state"],
        mimeType: mimeType ?? "",
        ondataavailable: null as RecorderLike["ondataavailable"],
        onstop: null as RecorderLike["onstop"],
        started: 0,
        stopped: 0,
        start() {
          this.state = "recording";
          this.started += 1;
        },
        stop() {
          this.state = "inactive";
          this.stopped += 1;
          this.onstop?.();
        },
        feed(data: string) {
          this.ondataavailable?.({ data: new Blob([data], { type: this.mimeType }) });
        },
      };
      made.push(recorder);
      return recorder;
    },
    isTypeSupported: (type) => types.includes(type),
    wakeLock: vi.fn(async () => {
      locks.taken += 1;
      return { release: async () => void (locks.released += 1) };
    }),
    now: () => now,
    every: (_ms, tick) => {
      ticks.push(tick);
      return () => ticks.splice(ticks.indexOf(tick), 1);
    },
  };
  return {
    deps,
    made,
    tracks,
    locks,
    ticks,
    advance(ms: number) {
      now += ms;
      for (const tick of [...ticks]) tick();
    },
  };
}

describe("the container", () => {
  it("is opus in webm where the phone has it, then ogg, then Safari's mp4", () => {
    expect(pickMimeType((type) => type === "audio/webm;codecs=opus")).toBe("audio/webm;codecs=opus");
    expect(pickMimeType((type) => type === "audio/ogg;codecs=opus")).toBe("audio/ogg;codecs=opus");
    expect(pickMimeType((type) => type === "audio/mp4")).toBe("audio/mp4");
    expect(pickMimeType(() => false)).toBeNull();
  });
});

describe("the consult recorder", () => {
  it("listens after start, counts the seconds, keeps the screen awake, and uploads nothing", async () => {
    const phone = fake();
    const recorder = new ConsultRecorder(phone.deps);
    expect(phone.deps.getUserMedia).not.toHaveBeenCalled();
    await recorder.start();
    expect(recorder.state.value).toBe("recording");
    expect(phone.made[0]!.started).toBe(1);
    expect(phone.locks.taken).toBe(1);
    phone.made[0]!.feed("the notice, then Dr Tan's yes");
    phone.advance(66_000);
    expect(recorder.elapsed.value).toBe(66);
  });

  it("hands back the whole recording once, on stop, and lets go of the microphone and the lock", async () => {
    const phone = fake();
    const recorder = new ConsultRecorder(phone.deps);
    await recorder.start();
    phone.made[0]!.feed("one");
    phone.advance(30_000);
    phone.made[0]!.feed("two");
    phone.advance(36_000);
    const kept = await recorder.stop();
    expect(kept).not.toBeNull();
    expect(await kept!.blob.text()).toBe("onetwo");
    expect(kept!.blob.type).toBe("audio/webm;codecs=opus");
    expect(kept!.durationS).toBe(66);
    expect(kept!.startedAt).toBe(new Date(1_000).toISOString());
    expect(recorder.state.value).toBe("stopped");
    expect(phone.tracks.stopped).toBe(1);
    expect(phone.locks.released).toBe(1);
    expect(phone.ticks).toHaveLength(0);
    // Stop again: the same recording, nothing new.
    expect(await recorder.stop()).toBe(kept);
  });

  it("throws the audio away on a no: nothing is kept, the microphone and the lock are let go", async () => {
    const phone = fake();
    const recorder = new ConsultRecorder(phone.deps);
    await recorder.start();
    phone.made[0]!.feed("the notice, then Dr Tan's no");
    recorder.discard();
    expect(recorder.state.value).toBe("discarded");
    expect(phone.made[0]!.stopped).toBe(1);
    expect(phone.tracks.stopped).toBe(1);
    expect(phone.locks.released).toBe(1);
    expect(await recorder.stop()).toBeNull();
  });

  it("says so when the phone will not give the microphone, and holds nothing", async () => {
    const phone = fake();
    phone.deps.getUserMedia = vi.fn(async () => Promise.reject(new Error("NotAllowedError")));
    const recorder = new ConsultRecorder(phone.deps);
    await expect(recorder.start()).rejects.toThrow("NotAllowedError");
    expect(recorder.state.value).toBe("idle");
    expect(phone.made).toHaveLength(0);
  });

  it("records where the phone has no wake lock", async () => {
    const phone = fake(["audio/mp4"]);
    phone.deps.wakeLock = async () => null;
    const recorder = new ConsultRecorder(phone.deps);
    await recorder.start();
    expect(phone.made[0]!.mimeType).toBe("audio/mp4");
    const kept = await recorder.stop();
    expect(kept!.blob.type).toBe("audio/mp4");
  });
});

describe("the pieces, as it records (#129)", () => {
  it("hands each piece to onData as the recorder hands it over, and keeps the whole for Stop", async () => {
    const f = fake();
    const recorder = new ConsultRecorder(f.deps);
    const pieces: Blob[] = [];
    await recorder.start();
    recorder.onData = (piece) => pieces.push(piece);
    f.made[0]!.feed("one");
    f.made[0]!.feed("two");
    expect(recorder.mimeType).toBe("audio/webm;codecs=opus");
    const kept = await recorder.stop();
    expect(await Promise.all(pieces.map((piece) => piece.text()))).toEqual(["one", "two"]);
    expect(await kept!.blob.text()).toBe("onetwo");
  });

  it("gives nothing more once thrown away", async () => {
    const f = fake();
    const recorder = new ConsultRecorder(f.deps);
    const pieces: Blob[] = [];
    await recorder.start();
    recorder.onData = (piece) => pieces.push(piece);
    recorder.discard();
    f.made[0]!.feed("late");
    expect(pieces).toEqual([]);
  });
});
