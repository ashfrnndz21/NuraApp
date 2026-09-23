/**
 * `POST /profiles/{id}/papers/{artifactId}/insight/stream` — "what it
 * means for you" (scene 8), the moment a paper is confirmed. This route
 * predates the unified `runs` event vocabulary (`backend/app/channels/api/
 * analyst.py`'s own doc: "the same event contract POST …/insights/stream
 * already promises") — a `step` event per real read, then one `report`
 * event — so it is parsed here on its own terms rather than forced
 * through `domain/runEvent.ts`'s `RunEvent` shape, which it does not use.
 */
import { fetch as expoFetch } from 'expo/fetch';

import { apiConfig, getSessionToken } from '../api/config';

export interface PaperInsightQuestion {
  insight_id: string;
  kind: string;
  text: string;
  ask_who: string;
}

export interface PaperInsightReport {
  report_id: string;
  headline: string;
  questions: PaperInsightQuestion[];
  boundary: string[];
  withheld: string[];
}

export type PaperInsightEvent =
  | { type: 'step'; key: string; label: string }
  | { type: 'report'; report: PaperInsightReport }
  | { type: 'refusal'; status: number; [key: string]: unknown };

export function streamPaperInsight(
  profileId: string,
  artifactId: string,
  onEvent: (event: PaperInsightEvent) => void,
): { done: Promise<void>; cancel: () => void } {
  const controller = new AbortController();
  const done = (async () => {
    const token = getSessionToken();
    const headers: Record<string, string> = { 'content-type': 'application/json' };
    if (token) headers.authorization = `Bearer ${token}`;
    const response = await expoFetch(`${apiConfig.baseUrl}/profiles/${profileId}/papers/${artifactId}/insight/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({}),
      signal: controller.signal,
    });
    if (!response.body) throw new Error(`paper insight stream: no response body (status ${response.status})`);
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
              if (json) onEvent(JSON.parse(json) as PaperInsightEvent);
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
