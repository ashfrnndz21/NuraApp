import { signal } from "@preact/signals";

/** The consult recorder (E02-05, E05-04): the phone's microphone, only after the notice.
 *
 *  `start()` asks for the microphone and starts the browser's `MediaRecorder` in the best
 *  container it has — opus in webm (Chrome, Android), opus in ogg (Firefox), AAC in mp4
 *  (Safari on the iPhone) — keeps the screen awake while it listens, and counts the seconds.
 *  The audio stays in the page's memory as the recorder hands it over: nothing is sent and
 *  nothing is written to the phone. `stop()` hands back the whole recording, once, for the
 *  screen to upload; `discard()` — a no from the doctor, or the page hidden before his answer
 *  — throws it away. Nothing here uploads, speaks or starts by itself
 *  (docs/adr/0006-consult-recording-on-the-web.md). */

export interface RecorderLike {
  readonly state: "inactive" | "recording" | "paused";
  readonly mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  start(timeslice?: number): void;
  stop(): void;
}

export interface StreamLike {
  getTracks(): { stop(): void }[];
}

export interface WakeLockLike {
  release(): Promise<void>;
}

export interface RecorderDeps {
  getUserMedia(): Promise<StreamLike>;
  makeRecorder(stream: StreamLike, mimeType: string | null): RecorderLike;
  isTypeSupported(type: string): boolean;
  /** A screen wake lock, where the browser has one; null where it does not. */
  wakeLock(): Promise<WakeLockLike | null>;
  now(): number;
  /** Call `tick` every `ms` until the returned function is called. */
  every(ms: number, tick: () => void): () => void;
}

/** The containers a phone's recorder makes, best first. */
export const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"] as const;

export function pickMimeType(isTypeSupported: (type: string) => boolean): string | null {
  return PREFERRED_TYPES.find((type) => isTypeSupported(type)) ?? null;
}

/** One recording as the phone kept it: the bytes, how long it listened, when it began. */
export interface Kept {
  blob: Blob;
  durationS: number;
  startedAt: string;
}

export type RecorderState = "idle" | "starting" | "recording" | "stopped" | "discarded";

export class ConsultRecorder {
  readonly state = signal<RecorderState>("idle");
  /** Seconds since the recorder started, for the timer beside the red dot. */
  readonly elapsed = signal(0);
  private chunks: Blob[] = [];
  private recorder: RecorderLike | null = null;
  private stream: StreamLike | null = null;
  private lock: WakeLockLike | null = null;
  private started = 0;
  private cancelTick: (() => void) | null = null;
  private kept: Kept | null = null;

  constructor(private readonly deps: RecorderDeps) {}

  /** Ask for the microphone and start listening. Call it after the notice has been said. */
  async start(): Promise<void> {
    if (this.state.peek() === "recording" || this.state.peek() === "starting") return;
    this.chunks = [];
    this.kept = null;
    this.state.value = "starting";
    try {
      const stream = await this.deps.getUserMedia();
      this.stream = stream;
      const recorder = this.deps.makeRecorder(stream, pickMimeType((type) => this.deps.isTypeSupported(type)));
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) this.chunks.push(event.data);
      };
      this.recorder = recorder;
      recorder.start(1000);
    } catch (failure) {
      this.release();
      this.state.value = "idle";
      throw failure;
    }
    this.started = this.deps.now();
    this.elapsed.value = 0;
    this.state.value = "recording";
    this.cancelTick = this.deps.every(500, () => {
      this.elapsed.value = (this.deps.now() - this.started) / 1000;
    });
    const lock = await this.deps.wakeLock().catch(() => null);
    if (this.state.peek() === "recording") this.lock = lock;
    else void lock?.release().catch(() => undefined);
  }

  /** Stop listening and hand back the whole recording. Nothing is sent from here. */
  stop(): Promise<Kept | null> {
    const recorder = this.recorder;
    if (!recorder || this.state.peek() !== "recording") return Promise.resolve(this.kept);
    const stoppedAt = this.deps.now();
    return new Promise((done) => {
      recorder.onstop = () => {
        const type = recorder.mimeType || this.chunks[0]?.type || "audio/webm";
        const kept: Kept = {
          blob: new Blob(this.chunks, { type }),
          durationS: Math.max(0, (stoppedAt - this.started) / 1000),
          startedAt: new Date(this.started).toISOString(),
        };
        this.kept = kept;
        this.chunks = [];
        this.release();
        this.elapsed.value = kept.durationS;
        this.state.value = "stopped";
        done(kept);
      };
      recorder.stop();
    });
  }

  /** Throw the recording away: a no, or the page hidden before the doctor answered. */
  discard(): void {
    const recorder = this.recorder;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      if (recorder.state !== "inactive") recorder.stop();
    }
    this.chunks = [];
    this.kept = null;
    this.release();
    this.state.value = "discarded";
  }

  private release(): void {
    this.cancelTick?.();
    this.cancelTick = null;
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    this.stream = null;
    this.recorder = null;
    void this.lock?.release().catch(() => undefined);
    this.lock = null;
  }
}

/** The browser's microphone, recorder, wake lock and clock. */
export function browserRecorderDeps(): RecorderDeps {
  return {
    getUserMedia: () => navigator.mediaDevices.getUserMedia({ audio: true }),
    makeRecorder: (stream, mimeType) =>
      new MediaRecorder(stream as MediaStream, mimeType ? { mimeType } : undefined) as unknown as RecorderLike,
    isTypeSupported: (type) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type),
    wakeLock: async () => {
      const locks = (navigator as Navigator & { wakeLock?: { request(kind: "screen"): Promise<WakeLockLike> } }).wakeLock;
      return locks ? locks.request("screen") : null;
    },
    now: () => Date.now(),
    every: (ms, tick) => {
      const id = setInterval(tick, ms);
      return () => clearInterval(id);
    },
  };
}

/** Whether this browser can record here at all. */
export function canRecord(): boolean {
  return typeof MediaRecorder !== "undefined" && typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}
