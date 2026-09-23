/**
 * The one event vocabulary (ADR 0019 point 4), read directly off
 * `backend/app/runtime/events.py`'s `EventBuilder`/`Event.to_json()` — field
 * names are the wire's own (snake_case), not re-cased, so a client can be
 * checked against the backend module by eye. `lib/ai`'s stream client
 * parses `POST /profiles/{id}/runs`' SSE frames straight into this type;
 * the fixture emitter in the same module produces the identical shape
 * (section 42 — swapping fixture for live is a call-site change, never a
 * consumer change).
 */

export type RunEventType =
  | 'RUN_STARTED'
  | 'RUN_FINISHED'
  | 'RUN_ERROR'
  | 'TEXT_MESSAGE_START'
  | 'TEXT_MESSAGE_CONTENT'
  | 'TEXT_MESSAGE_END'
  | 'TOOL_CALL_START'
  | 'TOOL_CALL_ARGS'
  | 'TOOL_CALL_END'
  | 'TOOL_CALL_RESULT'
  | 'STATE_SNAPSHOT'
  | 'STATE_DELTA'
  | 'CUSTOM';

/** `RUN_ERROR.code` — a closed set; never a Python exception's class name (events.py's own doc). */
export type RunErrorCode = 'refused' | 'not_found' | 'unknown_intent' | 'bad_request' | 'internal';

/** The closed shape a `TOOL_CALL_RESULT` may carry — never a row, never an extractor's free text. */
export interface ToolResult {
  key?: string;
  count?: number;
  document_kind?: string;
  linked_kind?: 'medicine' | 'visit';
  looking?: boolean;
  lines?: number;
  sections?: number;
  red_flag?: boolean;
}

/** RFC 6902 JSON Patch — the same representation AG-UI's own STATE_DELTA carries. */
export interface JsonPatchOp {
  op: 'add' | 'remove' | 'replace' | 'move' | 'copy' | 'test';
  path: string;
  value?: unknown;
  from?: string;
}

export type RunEvent =
  | { type: 'RUN_STARTED'; run_id: string; intent: string; seq: number; subject?: string }
  | { type: 'RUN_FINISHED'; run_id: string; intent: string; seq: number; result?: Record<string, unknown> }
  | { type: 'RUN_ERROR'; run_id: string; intent: string; seq: number; message: string; code: RunErrorCode }
  | { type: 'TEXT_MESSAGE_START'; run_id: string; intent: string; seq: number; message_id: string; role: string }
  | { type: 'TEXT_MESSAGE_CONTENT'; run_id: string; intent: string; seq: number; message_id: string; delta: string }
  | { type: 'TEXT_MESSAGE_END'; run_id: string; intent: string; seq: number; message_id: string }
  | {
      type: 'TOOL_CALL_START';
      run_id: string;
      intent: string;
      seq: number;
      tool_call_id: string;
      tool_call_name: string;
      /** The patient-words line a LoadingState shows while the call is in flight — never the bare tool name. */
      stage?: string;
    }
  | { type: 'TOOL_CALL_ARGS'; run_id: string; intent: string; seq: number; tool_call_id: string; delta: string }
  | { type: 'TOOL_CALL_END'; run_id: string; intent: string; seq: number; tool_call_id: string; error?: boolean }
  | {
      type: 'TOOL_CALL_RESULT';
      run_id: string;
      intent: string;
      seq: number;
      tool_call_id: string;
      content: ToolResult;
    }
  | { type: 'STATE_SNAPSHOT'; run_id: string; intent: string; seq: number; snapshot: Record<string, unknown> }
  | { type: 'STATE_DELTA'; run_id: string; intent: string; seq: number; patch: JsonPatchOp[] }
  | { type: 'CUSTOM'; run_id: string; intent: string; seq: number; name: string; value: Record<string, unknown> };

export type RunEventListener = (event: RunEvent) => void;

export type NuraIntent =
  | 'understand_paper'
  | 'answer_question'
  | 'generate_analysis'
  | 'generate_recommendations'
  | 'triage_red_flag'
  | 'prepare_visit';
