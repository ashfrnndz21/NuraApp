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

function enqueue<T>(work: () => Promise<T>, urgent = false): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const job: Job = { urgent, run: () => work().then(resolve, reject) };
    if (urgent) {
      const first = waiting.findIndex((one) => !one.urgent);
      waiting.splice(first < 0 ? waiting.length : first, 0, job);
    } else waiting.push(job);
    void pump();
  });
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
  return enqueue(() => send<T>(path, call), call.urgent);
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
  return enqueue(() => sendBlob(path, call), call.urgent);
}

async function sendBlob(path: string, call: Call): Promise<Blob> {
  const headers: Record<string, string> = { Accept: "audio/*" };
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  let response: Response;
  try {
    response = await fetch(urlFor(path, call), { method: "GET", headers, cache: "no-store", credentials: "omit" });
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

/** The same queue, for a body of bytes: a visit's recording, sent once on Stop (E02-05). */
export function apiUpload<T>(path: string, body: Blob, contentType: string, call: Call = {}): Promise<T> {
  return enqueue(() => sendBytes<T>(path, body, contentType, call), call.urgent);
}

async function sendBytes<T>(path: string, body: Blob, contentType: string, call: Call): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "Content-Type": contentType };
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  let response: Response;
  try {
    response = await fetch(urlFor(path, call), { method: "POST", headers, body, cache: "no-store", credentials: "omit" });
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

async function send<T>(path: string, call: Call): Promise<T> {
  const url = urlFor(path, call);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (call.body !== undefined) headers["Content-Type"] = "application/json";
  if (call.token) headers.Authorization = `Bearer ${call.token}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: call.method ?? "GET",
      headers,
      body: call.body === undefined ? null : JSON.stringify(call.body),
      cache: "no-store",
      credentials: "omit",
    });
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
