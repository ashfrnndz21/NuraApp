/**
 * Adapts the real backend wire event (`domain/runEvent.ts`'s `RunEvent`
 * — snake_case, exactly `app.runtime.events.EventBuilder`'s own field
 * names) onto the shape `AIState.consumeEvent` and `AIComposer` already
 * consume (`lib/ai/events.ts`'s `NuraEvent`, built for the Home spike's
 * fixture). Both shapes carry the identical AG-UI vocabulary (section
 * 42: swapping fixture for live changes a call site, never a consumer)
 * — this module is that seam, so neither `AIState` nor `AIComposer` has
 * to change to read a live run instead of a fixture one.
 *
 * `STATE_DELTA`'s real payload is an RFC 6902 JSON Patch against the
 * last `STATE_SNAPSHOT`, not the fixture's bare `{chips: [...]}` object
 * — this module holds that running snapshot per run and re-derives the
 * legacy `patch: {...}` shape from it after applying each patch, so a
 * `/chips` add/replace still reaches the composer the way it did before.
 */
import type { RunEvent } from '../../domain/runEvent';
import type { NuraEvent, NuraIntent } from './events';

function applyJsonPatch(
  target: Record<string, unknown>,
  ops: { op: string; path: string; value?: unknown }[],
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...target };
  for (const op of ops) {
    const key = op.path.replace(/^\//, '');
    if (!key || key.includes('/')) continue; // only top-level keys — this app's own payloads never nest deeper
    if (op.op === 'add' || op.op === 'replace') {
      next[key] = op.value;
    } else if (op.op === 'remove') {
      delete next[key];
    }
  }
  return next;
}

/**
 * One adapter per run: closes over the running `STATE_SNAPSHOT` so a
 * `STATE_DELTA`'s patch can be applied and the legacy `patch` object
 * re-derived from it.
 */
export function createRunEventAdapter() {
  let snapshot: Record<string, unknown> = {};

  return function adapt(event: RunEvent): NuraEvent {
    switch (event.type) {
      case 'RUN_STARTED':
        return { type: 'RUN_STARTED', runId: event.run_id, intent: event.intent as NuraIntent };
      case 'RUN_FINISHED':
        return { type: 'RUN_FINISHED', runId: event.run_id };
      case 'RUN_ERROR':
        return { type: 'RUN_ERROR', runId: event.run_id, message: event.message };
      case 'TEXT_MESSAGE_START':
        return {
          type: 'TEXT_MESSAGE_START',
          messageId: event.message_id,
          role: event.role === 'user' ? 'user' : 'assistant',
        };
      case 'TEXT_MESSAGE_CONTENT':
        return { type: 'TEXT_MESSAGE_CONTENT', messageId: event.message_id, delta: event.delta };
      case 'TEXT_MESSAGE_END':
        return { type: 'TEXT_MESSAGE_END', messageId: event.message_id };
      case 'TOOL_CALL_START':
        return {
          type: 'TOOL_CALL_START',
          toolCallId: event.tool_call_id,
          toolName: event.tool_call_name,
          label: event.stage ?? event.tool_call_name,
        };
      case 'TOOL_CALL_ARGS':
        return { type: 'TOOL_CALL_ARGS', toolCallId: event.tool_call_id, delta: event.delta };
      case 'TOOL_CALL_END':
        return { type: 'TOOL_CALL_END', toolCallId: event.tool_call_id };
      case 'TOOL_CALL_RESULT':
        return { type: 'TOOL_CALL_RESULT', toolCallId: event.tool_call_id, result: event.content };
      case 'STATE_SNAPSHOT':
        snapshot = { ...event.snapshot };
        return { type: 'STATE_SNAPSHOT', state: snapshot };
      case 'STATE_DELTA':
        snapshot = applyJsonPatch(snapshot, event.patch);
        return { type: 'STATE_DELTA', patch: snapshot };
      case 'CUSTOM':
        // No screen reads CUSTOM yet (the existing routes' migration escape, events.py's own
        // doc) — surfaced as a no-op STATE_DELTA so it is at least visible to a debugger,
        // never dropped silently.
        return { type: 'STATE_DELTA', patch: { custom: { name: event.name, value: event.value } } };
      default:
        return { type: 'STATE_DELTA', patch: {} };
    }
  };
}
