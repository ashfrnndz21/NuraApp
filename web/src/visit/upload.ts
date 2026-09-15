import { signal } from "@preact/signals";
import { Refused, Unreachable } from "../api/client";
import * as nura from "../api/nura";
import type { ConsultOut, UploadOut } from "../api/types";

/** A visit's recording sent in chunks as it is made, so a long visit survives a dropped
 *  connection (#129; the server's half is `backend/app/ingestion/chunks.py`).
 *
 *  Everything the recorder hands over (`add`) also stays in the page's memory until Stop
 *  (`ConsultRecorder`), so nothing is lost whatever the network does. The upload opens as the
 *  microphone opens. Then, every `SEND_EVERY_MS` and the moment the phone is back online, what
 *  the server does not have yet goes to it in pieces of at most `PIECE_BYTES`, one at a time,
 *  each numbered from where the server says it got to. A try that did not reach the server is
 *  only a try: the next one asks the server how far it got, and goes on from there. The
 *  doctor's yes goes the same way. `finish` (Stop) sends the rest and asks the server to put
 *  it together; `discard` (the doctor said no, or the page was left before he answered) throws
 *  the upload away on the server too, with every chunk already sent, in a call that goes even
 *  as the page goes. Nothing here records, speaks or decides: the Visit screen calls it. */

/** How often what the server does not have yet is sent while Nura listens. */
export const SEND_EVERY_MS = 30_000;
/** The most sent at once: about half a minute of opus, well under the server's cap. */
export const PIECE_BYTES = 256 * 1024;
/** The first chunk carries the container's header, which the server checks: it waits until
 *  there is at least this much, or Stop. */
export const FIRST_AT_LEAST = 16;
/** How many rounds one send, or one Stop, takes before it gives the network back. */
const ROUNDS = 5;

/** The server's refusals that mean its count and the phone's differ: ask it how far it got. */
const ASK_HOW_FAR: ReadonlySet<string> = new Set(["ChunkOutOfOrder", "NotTheChunkSent", "ChunkCutShort"]);
/** Its refusals that mean this upload takes nothing more: open a new one, send it all again. */
const START_AGAIN: ReadonlySet<string> = new Set(["UploadClosed", "NoSuchUpload"]);

export interface UploadCalls {
  open(contentType: string, startedAt: string): Promise<UploadOut>;
  status(uploadId: string): Promise<UploadOut>;
  chunk(uploadId: string, position: number, bytes: Blob): Promise<UploadOut>;
  yes(uploadId: string): Promise<UploadOut>;
  finish(uploadId: string, durationS: number): Promise<ConsultOut>;
  /** Throw it away on the server; nobody waits for the answer. */
  discard(uploadId: string, because: "no" | "left" | "whole"): void;
}

export interface UploadDeps {
  calls: UploadCalls;
  /** Call `tick` every `ms` until the returned function is called. */
  every(ms: number, tick: () => void): () => void;
  /** Call `back` whenever the phone is online again, until the returned function is called. */
  onOnline(back: () => void): () => void;
  /** Whether a failure is the network not answering, rather than the server saying no. */
  unreachable(failure: unknown): boolean;
  /** The refusal's name, when the server said no; null for anything else. */
  refusal(failure: unknown): string | null;
}

/** Stop came while the phone had no connection: try again when it is back. */
export class NoConnection extends Error {
  constructor() {
    super("no connection");
    this.name = "NoConnection";
  }
}

export class ChunkedUpload {
  /** False while the last try did not reach the server. */
  readonly connected = signal(true);
  private parts: Blob[] = [];
  private whole: Blob | null = null;
  private size = 0;
  private state: UploadOut | null = null;
  private unsure = false;
  private yes = false;
  private stopping = false;
  private over = false;
  private pending = false;
  /** The server let an upload lapse: before the doctor's yes, nothing more goes until it. */
  private lapsed = false;
  private failure: unknown = null;
  private flight: Promise<void> | null = null;
  private stops: (() => void)[] = [];

  constructor(
    private readonly deps: UploadDeps,
    private readonly contentType: string,
    private readonly startedAt: string,
  ) {}

  /** Open it and start sending: now, every `SEND_EVERY_MS`, and when the phone is back online. */
  start(): void {
    this.stops.push(this.deps.every(SEND_EVERY_MS, () => void this.send()));
    this.stops.push(this.deps.onOnline(() => void this.send()));
    void this.send();
  }

  /** A piece of audio, as the recorder handed it over. */
  add(piece: Blob): void {
    if (this.over || piece.size === 0) return;
    this.parts.push(piece);
    this.whole = null;
    this.size += piece.size;
  }

  /** The doctor said yes: sent now, or at the next try. */
  doctorSaidYes(): Promise<void> {
    this.yes = true;
    return this.send();
  }

  /** How many bytes of the recording the server has. */
  get sent(): number {
    return this.state?.received_bytes ?? 0;
  }

  get recorded(): number {
    return this.size;
  }

  /** Send what the server does not have yet. One try at a time: a call made while one is on
   *  its way runs again after it. A try that failed is kept for the next. */
  send(): Promise<void> {
    if (this.over) return Promise.resolve();
    this.pending = true;
    this.flight ??= this.rounds().finally(() => {
      this.flight = null;
    });
    return this.flight;
  }

  /** Stop: the rest sent, then the server asked to put it together. `NoConnection`, or the
   *  network's own failure, when the phone could not reach the server; a refusal as it came. */
  async finish(durationS: number): Promise<ConsultOut> {
    this.stopping = true;
    this.stopTimers();
    for (let round = 0; round < ROUNDS; round += 1) {
      await this.send();
      if (this.failure !== null) {
        const failure = this.failure;
        this.failure = null;
        throw failure;
      }
      if (!this.connected.value) throw new NoConnection();
      const state = this.state;
      if (state !== null && state.received_bytes >= this.size && (!this.yes || state.doctor_said_yes)) {
        const outcome = await this.deps.calls.finish(state.upload_id, durationS);
        this.close();
        return outcome;
      }
    }
    throw new NoConnection();
  }

  /** The doctor said no, or the page was left before he answered: thrown away here and on the
   *  server, with an open or a chunk still on its way thrown away after it lands. */
  discard(because: "no" | "left" | "whole"): void {
    if (this.over) return;
    this.close();
    const drop = () => {
      if (this.state !== null) this.deps.calls.discard(this.state.upload_id, because);
    };
    drop();
    if (this.flight !== null) void this.flight.then(drop);
  }

  private close(): void {
    this.over = true;
    this.stopTimers();
    this.parts = [];
    this.whole = null;
  }

  private stopTimers(): void {
    for (const stop of this.stops.splice(0)) stop();
  }

  private async rounds(): Promise<void> {
    for (let round = 0; round < ROUNDS && this.pending && !this.over; round += 1) {
      this.pending = false;
      try {
        await this.drain();
        this.connected.value = true;
        this.failure = null;
      } catch (failure) {
        if (!this.missed(failure)) return;
        this.pending = true;
      }
    }
  }

  /** What a failed try means for the next one; true to try again at once. */
  private missed(failure: unknown): boolean {
    if (this.deps.unreachable(failure)) {
      this.connected.value = false;
      this.unsure = true;
      return false;
    }
    this.connected.value = true;
    const refusal = this.deps.refusal(failure);
    if (refusal !== null && ASK_HOW_FAR.has(refusal)) {
      this.unsure = true;
      return true;
    }
    if (refusal !== null && START_AGAIN.has(refusal)) {
      this.state = null;
      this.lapsed = true;
      this.unsure = false;
      return true;
    }
    this.failure = failure;
    return false;
  }

  private all(): Blob {
    this.whole ??= new Blob(this.parts, { type: this.contentType });
    return this.whole;
  }

  private async drain(): Promise<void> {
    const { calls } = this.deps;
    if (this.state !== null && this.unsure) this.state = await calls.status(this.state.upload_id);
    this.unsure = false;
    // Lapsed on the server: once the doctor has said yes, a new one, sent again from the start;
    // before his answer, nothing more goes until he says yes.
    if (this.state !== null && !this.state.open) {
      this.state = null;
      this.lapsed = true;
    }
    if (this.state === null && this.lapsed && !this.yes) return;
    this.state ??= await calls.open(this.contentType, this.startedAt);
    if (this.over) return;
    if (this.yes && !this.state.doctor_said_yes) this.state = await calls.yes(this.state.upload_id);
    while (!this.over && this.state.received_bytes < this.size) {
      const from = this.state.received_bytes;
      if (from === 0 && this.size < FIRST_AT_LEAST && !this.stopping) return;
      const to = Math.min(this.size, from + Math.min(PIECE_BYTES, this.state.max_chunk_bytes));
      this.state = await calls.chunk(this.state.upload_id, this.state.chunks, this.all().slice(from, to));
    }
  }
}

/** The calls, for one visit, with this key. */
export function uploadCalls(token: string, profileId: string, appointmentId: string): UploadCalls {
  return {
    open: (contentType, startedAt) => nura.openUpload(token, profileId, appointmentId, contentType, startedAt),
    status: (uploadId) => nura.uploadStatus(token, profileId, appointmentId, uploadId),
    chunk: (uploadId, position, bytes) => nura.uploadChunk(token, profileId, appointmentId, uploadId, position, bytes),
    yes: (uploadId) => nura.doctorSaidYes(token, profileId, appointmentId, uploadId),
    finish: (uploadId, durationS) => nura.finishUpload(token, profileId, appointmentId, uploadId, durationS),
    discard: (uploadId, because) => nura.discardUpload(token, profileId, appointmentId, uploadId, because),
  };
}

/** The browser's timers and its online event. */
export function browserUploadDeps(calls: UploadCalls): UploadDeps {
  return {
    calls,
    every: (ms, tick) => {
      const id = setInterval(tick, ms);
      return () => clearInterval(id);
    },
    onOnline: (back) => {
      window.addEventListener("online", back);
      return () => window.removeEventListener("online", back);
    },
    unreachable: (failure) => failure instanceof Unreachable,
    refusal: (failure) => (failure instanceof Refused ? failure.refusal : null),
  };
}

/** Whether a failure means the phone could not reach the server. */
export function isNoConnection(failure: unknown): boolean {
  return failure instanceof NoConnection || failure instanceof Unreachable;
}
