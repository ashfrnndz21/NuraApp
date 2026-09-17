import type { RefusalBody } from "./types";

/** The API is on the same origin as the app, under `/api` (see
 *  `backend/app/channels/api/__init__.py`); Vite proxies it in dev. */
export const API_BASE = "/api";

/** The backend said no. `refusal` is the class name and is mapped to one plain sentence by
 *  `refusalSentence`; it is never shown as it is. */
export class Refused extends Error {
  constructor(
    readonly refusal: string,
    readonly status: number,
    readonly scope?: string,
  ) {
    super(`refused: ${refusal} (${status})`);
    this.name = "Refused";
  }
}

/** The network did not answer at all: offline, or the server is not there. */
export class Unreachable extends Error {
  constructor() {
    super("unreachable");
    this.name = "Unreachable";
  }
}

export interface Call {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** For `apiBlob`: what kind of bytes to ask for (a card's voice by default). */
  accept?: string;
  token?: string | null;
  query?: Record<string, string | undefined>;
  /** Goes ahead of every call still waiting (see `enqueue`): the red-flag path only. */
  urgent?: boolean;
  /** Waits as long as the server takes: putting a visit's recording together and hearing it
   *  (#129). Any other call gives up after `CALL_DEADLINE_MS`. */
  slow?: boolean;
}

function isRefusalBody(value: unknown): value is RefusalBody {
  return typeof value === "object" && value !== null && typeof (value as RefusalBody).refusal === "string";
}

/** A body read as JSON when it is JSON; anything else (a proxy's page, an empty body) is null. */
function parseJson(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** A "no" with no refusal in it — a proxy or a layer in front of the app answering for it — by
 *  its status: a body too large to take is `TooLarge`, and said in its own sentence. */
function bareRefusal(status: number): string {
  if (status === 422) return "NotWellFormed";
  if (status === 413) return "TooLarge";
  return "HttpError";
}

/** Calls go out one at a time. The person does one thing at a time, and the local dev
 *  database (SQLite) refuses two requests that each read and then write their audit line
 *  at once; a queue costs a few milliseconds and makes the app's behaviour the same on a
 *  laptop as on the deployment.
 *
 *  An `urgent` call — a red word on the feeling cloud, the not-feeling-well button, a symptom
 *  logged — goes next: ahead of every call still waiting, and ahead too of a background read
 *  already on the wire when it was made (a page's own refresh, a feed's prefetch, a restore
 *  after sign-in) — that read is aborted, its caller sees `Unreachable` and copes exactly as
 *  it would with no network, and the urgent call is sent in its place. A write already on the
 *  wire (a tap held offline being replayed, a nudge answered) is left to finish: it cannot be
 *  taken back once the backend may have seen it, so the urgent call waits the moment or two
 *  that takes, never longer. A red word reaches the flag before any page read, whatever was
 *  queued first or already sending (W7, E13-02, E17-01, E17-02, E17-04). */
interface Job {
  urgent: boolean;
  /** A read with no side effect: safe to abort and let its caller coldly fail, since nothing
   *  it does is lost by not finishing. A write is never abortable — once it may be on the
   *  wire, taking it back is not this queue's to decide. */
  abortable: boolean;
  control: AbortController;
  run: () => Promise<void>;
}
const waiting: Job[] = [];
let sending = false;
/** The job presently inside `run()` — on the wire, not merely waiting — so an urgent call
 *  arriving behind it can still reach past it (see `enqueue`). */
let current: Job | null = null;

/** Held while a screen that may end in a red word is open (the not-feeling-well flow):
 *  `holdBackground`/`releaseBackground`, called from that screen's own mount and unmount.
 *  A background read already on the wire when the hold starts is left to finish — it is not
 *  urgent yet, and aborting it for no reason wastes it — but no *further* one is dispatched
 *  while held, whatever is still waiting. This does not replace the urgent-arrival abort in
 *  `enqueue` (a read can still be on the wire the instant he actually sends his words, and
 *  that is still caught there); it only closes the much likelier gap: a background read that
 *  starts and finishes on its own schedule in the seconds between opening the screen and
 *  speaking, which no abort can undo once the response is already back on the wire (a real
 *  CI race, `tests/e2e/day.spec.ts`'s "a red word said out loud"). Held reads resume the
 *  moment the hold is released, in the order they were queued. */
let held = false;

export function holdBackground(): void {
  held = true;
}

export function releaseBackground(): void {
  held = false;
  void pump();
}

/** How long an urgent call may take from the tap before it is given up as unreachable, whatever
 *  is on the wire: the red-flag path shows the backend's offline card then, never a page that
 *  waits (W7, ADR 0012). A call still waiting then is taken out of the queue and never sent; one
 *  on the wire is aborted. */
export const URGENT_DEADLINE_MS = 10_000;

/** How long any other call may hang before it is given up as unreachable, so that one stuck
 *  request never holds the queue — and an urgent call behind it — for ever. */
export const CALL_DEADLINE_MS = 30_000;

function enqueue<T>(work: (signal: AbortSignal) => Promise<T>, urgent = false, abortable = false): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const control = new AbortController();
    let settled = false;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    const settle = (done: () => void) => {
      if (settled) return;
      settled = true;
      if (deadline !== undefined) clearTimeout(deadline);
      done();
    };
    const job: Job = {
      urgent,
      abortable,
      control,
      run: () =>
        settled
          ? Promise.resolve()
          : work(control.signal).then(
              (value) => settle(() => resolve(value)),
              (failure: unknown) => settle(() => reject(failure)),
            ),
    };
    if (urgent) {
      const first = waiting.findIndex((one) => !one.urgent);
      waiting.splice(first < 0 ? waiting.length : first, 0, job);
      // Nothing that only reads may sit ahead of a red word, whether it is still waiting
      // (the splice above) or already sending: a background refresh caught on the wire is
      // stopped here, not left to decide by whatever moment it happened to start.
      if (current && !current.urgent && current.abortable) current.control.abort();
      deadline = setTimeout(
        () =>
          settle(() => {
            const at = waiting.indexOf(job);
            if (at >= 0) waiting.splice(at, 1);
            control.abort();
            reject(new Unreachable());
          }),
        URGENT_DEADLINE_MS,
      );
    } else waiting.push(job);
    void pump();
  });
}

/** A fetch that gives up after `within` ms (`CALL_DEADLINE_MS`; 0 waits as long as it takes), or
 *  when the call's own signal aborts. */
async function fetchWithin(url: URL, init: RequestInit, signal: AbortSignal, within = CALL_DEADLINE_MS): Promise<Response> {
  const control = new AbortController();
  const stop = () => control.abort();
  const timer = within > 0 ? setTimeout(stop, within) : undefined;
  if (signal.aborted) stop();
  else signal.addEventListener("abort", stop, { once: true });
  try {
    return await fetch(url, { ...init, signal: control.signal });
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", stop);
  }
}

/** The next job to send: none, while held, unless a red word has actually reached the queue
 *  (`held` never blocks an urgent call — only ever what is still merely waiting). */
function next(): Job | undefined {
  if (!held) return waiting.shift();
  const at = waiting.findIndex((one) => one.urgent);
  return at < 0 ? undefined : waiting.splice(at, 1)[0];
}

async function pump(): Promise<void> {
  if (sending) return;
  sending = true;
  try {
    for (let job = next(); job; job = next()) {
      current = job;
      await job.run();
    }
  } finally {
    current = null;
    sending = false;
  }
}

/** One call to the API. Bearer token in a header, never a cookie; JSON in and out. A `GET` is
 *  the only shape a background read takes here, and the only shape it is safe to abort for an
 *  urgent call arriving behind it (see `enqueue`). */
export function api<T>(path: string, call: Call = {}): Promise<T> {
  return enqueue((signal) => send<T>(path, call, signal), call.urgent, (call.method ?? "GET") === "GET");
}

function urlFor(path: string, call: Call): URL {
  const url = new URL(API_BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(call.query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, value);
  }
  return url;
}

/** The same queue, for bytes: a card's pre-rendered voice (E11). A Blob on success; a refusal
 *  as `Refused`; a 404 that is not a refusal — the route is not on this backend yet — as
 *  `Refused("NotFound", 404)`, so the caller can tell "no such route" from "no". */
export function apiBlob(path: string, call: Call = {}): Promise<Blob> {
  return enqueue((signal) => sendBlob(path, call, signal), call.urgent, true);
}

async function sendBlob(path: string, call: Call, signal: AbortSignal): Promise<Blob> {
  const headers: Record<string, string> = { Accept: call.accept ?? "audio/*" };
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  let response: Response;
  try {
    response = await fetch(urlFor(path, call), { method: "GET", headers, cache: "no-store", credentials: "omit", signal });
  } catch {
    throw new Unreachable();
  }
  if (!response.ok) {
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(await response.text());
    } catch {
      /* not JSON: not a refusal */
    }
    if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
    throw new Refused(response.status === 404 ? "NotFound" : bareRefusal(response.status), response.status);
  }
  return response.blob();
}

/** The same queue, for a page of text: a printable page the backend renders — the emergency
 *  card (E13-01), kept on the phone to print with no network, and the consent record. The text
 *  on success; a refusal as `Refused`, the way `apiBlob` says it. */
export function apiText(path: string, call: Call = {}): Promise<string> {
  return enqueue(async (signal) => {
    const headers: Record<string, string> = { Accept: "text/html" };
    if (call.token) headers.Authorization = `Bearer ${call.token}`;
    let response: Response;
    try {
      response = await fetchWithin(urlFor(path, call), { method: "GET", headers, cache: "no-store", credentials: "omit" }, signal);
    } catch {
      throw new Unreachable();
    }
    const text = await response.text();
    if (!response.ok) {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(text);
      } catch {
        /* not JSON: not a refusal */
      }
      if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
      throw new Refused(response.status === 404 ? "NotFound" : bareRefusal(response.status), response.status);
    }
    return text;
  }, call.urgent, true);
}

/** The same queue, for a body of bytes: a visit's recording, sent once on Stop (E02-05). Always
 *  a write (`sendBytes` is `POST` only): never abortable, the same as any other write. */
export function apiUpload<T>(path: string, body: Blob, contentType: string, call: Call = {}): Promise<T> {
  return enqueue((signal) => sendBytes<T>(path, body, contentType, call, signal), call.urgent, false);
}

async function sendBytes<T>(path: string, body: Blob, contentType: string, call: Call, signal: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "Content-Type": contentType };
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  let response: Response;
  try {
    response = await fetch(urlFor(path, call), { method: "POST", headers, body, cache: "no-store", credentials: "omit", signal });
  } catch {
    throw new Unreachable();
  }
  return answer<T>(response);
}

/** The same queue, for one chunk of a visit's recording (#129): its bytes, by `call.method`
 *  (PUT), given up after `CALL_DEADLINE_MS` like any call so that a chunk on a bad network never
 *  holds the queue. The chunked upload sends it again, from where the server got to. */
export function apiBytes<T>(path: string, body: Blob, contentType: string, call: Call = {}): Promise<T> {
  return enqueue(async (signal) => {
    const headers: Record<string, string> = { Accept: "application/json", "Content-Type": contentType };
    if (call.token) headers.Authorization = `Bearer ${call.token}`;
    let response: Response;
    try {
      response = await fetchWithin(
        urlFor(path, call),
        { method: call.method ?? "PUT", headers, body, cache: "no-store", credentials: "omit" },
        signal,
      );
    } catch {
      throw new Unreachable();
    }
    return answer<T>(response);
  }, call.urgent);
}

/** A call that must go even as the page goes, outside the queue and waited for by nobody:
 *  throwing away a visit's recording when the doctor said no or the page was left (#129). If
 *  it cannot go, the server throws the upload away itself (`app.ingestion.chunks`). */
export function sendAndForget(path: string, call: Call = {}): void {
  const headers: Record<string, string> = {};
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  try {
    void fetch(urlFor(path, call), {
      method: call.method ?? "POST",
      headers,
      keepalive: true,
      cache: "no-store",
      credentials: "omit",
    }).catch(() => undefined);
  } catch {
    /* the page is going; the server's sweep has it */
  }
}

/** One event off a stream: a plain object with at least a `type`, the shape `Call.body`'s
 *  route defines (`ask/stream`, `find/stream`). Streamed events carry the same `why`/citation
 *  ids the final answer does and nothing else — no health data beyond the name of the part
 *  being read (docs/design-direction.md "Conversation, waiting and thinking"). */
export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

/** The same queue, for a Server-Sent Events stream: the ask bar and the feed's web and video
 *  search (E03-05, E21). Each `data: ` line is one JSON event, handed to `onEvent` the moment
 *  it arrives — never buffered to look like it took longer. A refusal arrives as an event too
 *  (`{type: "refusal", refusal, scope?}`), thrown here as `Refused`, exactly as a plain call
 *  throws it, so a caller copes with either the same way.
 *
 *  No single deadline covers the whole stream — a real answer may legitimately take longer
 *  than one request — but the connection is under the same `CALL_DEADLINE_MS` as an *idle*
 *  timeout, reset on every event received: a stream that stalls (nothing arrives, ever) still
 *  ends in `Unreachable` within the deadline rather than spinning for ever (#193). */
export function apiStream(path: string, call: Call, onEvent: (event: StreamEvent) => void): Promise<void> {
  return enqueue((signal) => sendStream(path, call, onEvent, signal), call.urgent, true);
}

async function sendStream(
  path: string,
  call: Call,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (call.body !== undefined) headers["Content-Type"] = "application/json";
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  const control = new AbortController();
  const stop = () => control.abort();
  if (signal.aborted) stop();
  else signal.addEventListener("abort", stop, { once: true });
  let idle: ReturnType<typeof setTimeout> | undefined;
  const resetIdle = () => {
    if (idle !== undefined) clearTimeout(idle);
    idle = setTimeout(stop, CALL_DEADLINE_MS);
  };
  resetIdle();
  try {
    let response: Response;
    try {
      response = await fetch(urlFor(path, call), {
        method: call.method ?? "POST",
        headers,
        body: call.body === undefined ? null : JSON.stringify(call.body),
        cache: "no-store",
        credentials: "omit",
        signal: control.signal,
      });
    } catch {
      throw new Unreachable();
    }
    if (!response.ok || !response.body) {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(await response.text());
      } catch {
        /* not JSON: not a refusal */
      }
      if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
      throw new Refused(response.status === 404 ? "NotFound" : bareRefusal(response.status), response.status);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch {
        throw new Unreachable();
      }
      if (chunk.done) break;
      resetIdle();
      buffer += decoder.decode(chunk.value, { stream: true });
      let at: number;
      while ((at = buffer.indexOf("\n\n")) >= 0) {
        const raw = buffer.slice(0, at);
        buffer = buffer.slice(at + 2);
        const line = raw.split("\n").find((one) => one.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice("data: ".length)) as StreamEvent;
        if (event.type === "refusal") {
          throw new Refused(String(event.refusal), Number(event.status ?? 400), event.scope as string | undefined);
        }
        onEvent(event);
      }
    }
  } finally {
    clearTimeout(idle);
    signal.removeEventListener("abort", stop);
  }
}

async function answer<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const parsed = parseJson(await response.text());
  if (!response.ok) {
    if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
    throw new Refused(bareRefusal(response.status), response.status);
  }
  return parsed as T;
}

async function send<T>(path: string, call: Call, signal: AbortSignal): Promise<T> {
  const url = urlFor(path, call);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (call.body !== undefined) headers["Content-Type"] = "application/json";
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  let response: Response;
  try {
    response = await fetchWithin(
      url,
      {
        method: call.method ?? "GET",
        headers,
        body: call.body === undefined ? null : JSON.stringify(call.body),
        cache: "no-store",
        credentials: "omit",
      },
      signal,
      call.slow ? 0 : CALL_DEADLINE_MS,
    );
  } catch {
    throw new Unreachable();
  }
  if (response.status === 204) return undefined as T;
  return answer<T>(response);
}
