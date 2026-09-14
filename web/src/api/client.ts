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
 *  laptop as on the deployment. */
let queue: Promise<unknown> = Promise.resolve();

/** One call to the API. Bearer token in a header, never a cookie; JSON in and out. */
export function api<T>(path: string, call: Call = {}): Promise<T> {
  const next = queue.then(() => send<T>(path, call));
  queue = next.catch(() => undefined);
  return next;
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
  const next = queue.then(() => sendBlob(path, call));
  queue = next.catch(() => undefined);
  return next;
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
    throw new Refused(response.status === 404 ? "NotFound" : bareRefusal(response.status), response.status);
  }
  return response.blob();
}

/** The same queue, for a page of HTML: the emergency card's printable page (E13-01), kept on
 *  the phone for printing with no network. A refusal is `Refused`, as everywhere. */
export function apiText(path: string, call: Call = {}): Promise<string> {
  const next = queue.then(() => sendText(path, call));
  queue = next.catch(() => undefined);
  return next;
}

async function sendText(path: string, call: Call): Promise<string> {
  const headers: Record<string, string> = { Accept: "text/html" };
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
    throw new Refused(bareRefusal(response.status), response.status);
  }
  return response.text();
}

/** The same queue, for a body of bytes: a visit's recording, sent once on Stop (E02-05). */
export function apiUpload<T>(path: string, body: Blob, contentType: string, call: Call = {}): Promise<T> {
  const next = queue.then(() => sendBytes<T>(path, body, contentType, call));
  queue = next.catch(() => undefined);
  return next;
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
  const parsed = parseJson(await response.text());
  if (!response.ok) {
    if (isRefusalBody(parsed)) throw new Refused(parsed.refusal, response.status, parsed.scope);
    throw new Refused(bareRefusal(response.status), response.status);
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
  return answer<T>(response);
}
