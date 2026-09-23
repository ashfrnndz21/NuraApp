/**
 * The live event-stream client for `POST /profiles/{id}/runs`
 * (`backend/app/channels/api/runs.py`; ADR 0019 point 5): one Nura Run,
 * as the typed `RunEvent` vocabulary (`domain/runEvent.ts`), parsed
 * straight off the SSE wire — `data: <json>\n\n` frames, exactly
 * `app.runtime.events.to_sse`'s own serialiser.
 *
 * Uses `expo/fetch` (already part of the `expo` package — no new
 * dependency), not the RN built-in global `fetch`: only `expo/fetch`
 * exposes a real `ReadableStream` on `response.body` on native, which a
 * server-sent stream needs to be read incrementally rather than only
 * after the connection closes.
 */
import { fetch as expoFetch } from 'expo/fetch';

import { apiConfig, getSessionToken } from '../api/config';
import type { NuraIntent, RunEvent } from '../../domain/runEvent';
import { createRunEventAdapter } from './adaptRunEvent';
import type { NuraEventListener } from './events';

export interface RunStreamHandle {
  /** Resolves once RUN_FINISHED or RUN_ERROR has been yielded, or the stream ends unexpectedly. */
  done: Promise<void>;
  cancel: () => void;
}

/**
 * Streams one run, calling `onEvent` for each `RunEvent` as it arrives —
 * never buffered and replayed, so a caller driving `AIState.consumeEvent`
 * from `onEvent` sees the same real-time shape a fixture run gives it
 * (section 42).
 */
export function streamNuraRun(
  profileId: string,
  intent: NuraIntent,
  payload: Record<string, unknown>,
  onEvent: (event: RunEvent) => void,
): RunStreamHandle {
  const controller = new AbortController();

  const done = (async () => {
    const token = getSessionToken();
    const headers: Record<string, string> = { 'content-type': 'application/json' };
    if (token) headers.authorization = `Bearer ${token}`;

    const response = await expoFetch(`${apiConfig.baseUrl}/profiles/${profileId}/runs`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ intent, payload }),
      signal: controller.signal,
    });

    if (!response.body) {
      throw new Error(`Nura run stream: no response body (status ${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          for (const line of frame.split('\n')) {
            if (line.startsWith('data:')) {
              const json = line.slice(5).trim();
              if (json) onEvent(JSON.parse(json) as RunEvent);
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } finally {
      reader.releaseLock();
    }
  })();

  return { done, cancel: () => controller.abort() };
}

/**
 * The drop-in replacement for `runAskFixture`/`runExplainFixture`
 * (`lib/ai/events.ts`) once a screen is ready to leave demo mode: same
 * `{done, cancel}` shape, same `NuraEventListener` callback, a real run
 * on the wire underneath. `AIComposer`'s `onEvent` (and anything else
 * built against the fixture shape) needs no change to call this instead
 * — the adapter is the whole seam (section 42).
 */
export function runNuraLive(
  profileId: string,
  intent: NuraIntent,
  payload: Record<string, unknown>,
  onEvent: NuraEventListener,
): RunStreamHandle {
  const adapt = createRunEventAdapter();
  return streamNuraRun(profileId, intent, payload, (event) => onEvent(adapt(event)));
}
