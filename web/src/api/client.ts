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
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  token?: string | null;
  query?: Record<string, string | undefined>;
  /** Goes ahead of every call still waiting (see `enqueue`): the red-flag path only. */
  urgent?: boolean;
}

function isRefusalBody(value: unknown): value is RefusalBody {
  return typeof value === "object" && value !== null && typeof (value as RefusalBody).refusal === "string";
}

/** Calls go out one at a time. The person does one thing at a time, and the local dev
 *  database (SQLite) refuses two requests that each read and then write their audit line
 *  at once; a queue costs a few milliseconds and makes the app's behaviour the same on a
 *  laptop as on the deployment.
 *
 *  An `urgent` call — a red word on the feeling cloud, the not-feeling-well button — goes
 *  next: ahead of every call still waiting, behind only the one already on the wire (and any
 *  urgent call before it). A red word reaches the flag before any page read that was queued
 *  first (W7, E13-02, E17-02). */
interface Job {
  urgent: boolean;
  run: () => Promise<void>;
}
const waiting: Job[] = [];
let sending = false;

/** How long an urgent call may take from the tap before it is given up as unreachable, whatever
 *  is on the wire: the red-flag path shows the backend's offline card then, never a page that
 *  waits (W7, ADR 0012). A call still waiting then is taken out of the queue and never sent; one
 *  on the wire is aborted. */
export const URGENT_DEADLINE_MS = 10_000;

/** How long any other call may hang before it is given up as unreachable, so that one stuck
 *  request never holds the queue — and an urgent call behind it — for ever. */
export const CALL_DEADLINE_MS = 30_000;

function enqueue<T>(work: (signal: AbortSignal) => Promise<T>, urgent = false): Promise<T> {
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

/** A fetch that gives up after `CALL_DEADLINE_MS`, or when the call's own signal aborts. */
async function fetchWithin(url: URL, init: RequestInit, signal: AbortSignal): Promise<Response> {
  const control = new AbortController();
  const stop = () => control.abort();
  const timer = setTimeout(stop, CALL_DEADLINE_MS);
  if (signal.aborted) stop();
  else signal.addEventListener("abort", stop, { once: true });
  try {
    return await fetch(url, { ...init, signal: control.signal });
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", stop);
  }
}

async function pump(): Promise<void> {
  if (sending) return;
  sending = true;
  try {
    for (let job = waiting.shift(); job; job = waiting.shift()) await job.run();
  } finally {
    sending = false;
  }
}

/** One call to the API. Bearer token in a header, never a cookie; JSON in and out. */
export function api<T>(path: string, call: Call = {}): Promise<T> {
  return enqueue((signal) => send<T>(path, call, signal), call.urgent);
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
  return enqueue((signal) => sendBlob(path, call, signal), call.urgent);
}

async function sendBlob(path: string, call: Call, signal: AbortSignal): Promise<Blob> {
  const headers: Record<string, string> = { Accept: "audio/*" };
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
    throw new Refused(response.status === 404 ? "NotFound" : "HttpError", response.status);
  }
  return response.blob();
}

/** The same queue, for a page of text: a printable page the backend renders (the consent
 *  record). The text on success; a refusal as `Refused`, the way `apiBlob` says it. */
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
      throw new Refused(response.status === 404 ? "NotFound" : "HttpError", response.status);
    }
    return text;
  }, call.urgent);
}

/** The same queue, for a body of bytes: a visit's recording, sent once on Stop (E02-05). */
export function apiUpload<T>(path: string, body: Blob, contentType: string, call: Call = {}): Promise<T> {
  return enqueue((signal) => sendBytes<T>(path, body, contentType, call, signal), call.urgent);
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

async function answer<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
    throw new Refused(response.status === 422 ? "NotWellFormed" : "HttpError", response.status);
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
    );
  } catch {
    throw new Unreachable();
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
    throw new Refused(response.status === 422 ? "NotWellFormed" : "HttpError", response.status);
  }
  return parsed as T;
}
