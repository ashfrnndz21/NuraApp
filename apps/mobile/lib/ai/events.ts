/**
 * The one event vocabulary (ADR 0019 §4), AG-UI-shaped. The UI consumes
 * this stream and never knows whether the intelligence came from a model,
 * deterministic code, or — as here — a fixture. Motion represents real
 * state and never fakes time: every ms below is spent actually waiting,
 * not decoration.
 *
 * The fixture emitter in this file produces exactly the event shape that
 * `POST /profiles/{id}/runs` (ADR 0019 §5, `runNura`) will emit once it
 * exists; swapping the fixture for the live route is a configuration
 * change in `lib/api`, not a change to any consumer of this stream.
 */
import { streamBody, thinkHold } from '../../components/motion/motionTokens';

export type NuraIntent =
  | 'understand_paper'
  | 'answer_question'
  | 'generate_analysis'
  | 'prepare_visit'
  | 'generate_recommendations'
  | 'triage_red_flag';

export interface NuraRunRequest {
  intent: NuraIntent;
  subject: string;
  context?: Record<string, unknown>;
}

export type NuraEvent =
  | { type: 'RUN_STARTED'; runId: string; intent: NuraIntent }
  | { type: 'TEXT_MESSAGE_START'; messageId: string; role: 'user' | 'assistant' }
  | { type: 'TEXT_MESSAGE_CONTENT'; messageId: string; delta: string }
  | { type: 'TEXT_MESSAGE_END'; messageId: string }
  | { type: 'TOOL_CALL_START'; toolCallId: string; toolName: string; label: string }
  | { type: 'TOOL_CALL_ARGS'; toolCallId: string; delta: string }
  | { type: 'TOOL_CALL_END'; toolCallId: string }
  | { type: 'TOOL_CALL_RESULT'; toolCallId: string; result: unknown }
  | { type: 'STATE_SNAPSHOT'; state: Record<string, unknown> }
  | { type: 'STATE_DELTA'; patch: Record<string, unknown> }
  | { type: 'RUN_FINISHED'; runId: string }
  | { type: 'RUN_ERROR'; runId: string; message: string };

export type NuraEventListener = (event: NuraEvent) => void;

/** One word/punctuation-preserving chunker, so TEXT_MESSAGE_CONTENT arrives the way a stream really would. */
function chunk(sentence: string): string[] {
  const parts = sentence.match(/\S+\s*/g);
  return parts ?? [sentence];
}

let runCounter = 0;
let messageCounter = 0;

export interface AskFixtureAnswer {
  question: string;
  stage: string;
  contextFirst: string;
  followUp: string;
  explain: string;
  chips: readonly string[];
}

/**
 * Emits the composer's fixture run: a context-first answer, one question
 * back, then chips — the ADR 0019 §4 vocabulary end to end. Cancellable
 * via the returned `cancel()`; every await is a real wait on a token
 * from `motionTokens`, so a caller measuring frame time over this run is
 * measuring the real animated path.
 */
export function runAskFixture(
  answer: AskFixtureAnswer,
  onEvent: NuraEventListener
): { done: Promise<void>; cancel: () => void } {
  let cancelled = false;
  const runId = `run_${++runCounter}`;
  const wait = (ms: number) =>
    new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => (cancelled ? reject(new Error('cancelled')) : resolve()), ms);
      // eslint-disable-next-line @typescript-eslint/no-unused-expressions
      cancelHooks.push(() => clearTimeout(t));
    });
  const cancelHooks: Array<() => void> = [];

  const done = (async () => {
    try {
      onEvent({ type: 'RUN_STARTED', runId, intent: 'answer_question' });

      const userMsgId = `msg_${++messageCounter}`;
      onEvent({ type: 'TEXT_MESSAGE_START', messageId: userMsgId, role: 'user' });
      for (const word of chunk(answer.question)) {
        if (cancelled) return;
        onEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: userMsgId, delta: word });
        await wait(streamBody);
      }
      onEvent({ type: 'TEXT_MESSAGE_END', messageId: userMsgId });

      const toolCallId = `tool_${runId}`;
      onEvent({ type: 'TOOL_CALL_START', toolCallId, toolName: 'read_own_record', label: answer.stage });
      await wait(thinkHold);
      if (cancelled) return;
      onEvent({ type: 'TOOL_CALL_END', toolCallId });
      onEvent({ type: 'TOOL_CALL_RESULT', toolCallId, result: { ok: true } });

      // Context first (spec §10) — its own message.
      const contextMsgId = `msg_${++messageCounter}`;
      onEvent({ type: 'TEXT_MESSAGE_START', messageId: contextMsgId, role: 'assistant' });
      for (const word of chunk(answer.contextFirst)) {
        if (cancelled) return;
        onEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: contextMsgId, delta: word });
        await wait(streamBody);
      }
      onEvent({ type: 'TEXT_MESSAGE_END', messageId: contextMsgId });

      // Then one question back — a second message, so the UI can style it apart.
      const followUpMsgId = `msg_${++messageCounter}`;
      onEvent({ type: 'TEXT_MESSAGE_START', messageId: followUpMsgId, role: 'assistant' });
      for (const word of chunk(answer.followUp)) {
        if (cancelled) return;
        onEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: followUpMsgId, delta: word });
        await wait(streamBody);
      }
      onEvent({ type: 'TEXT_MESSAGE_END', messageId: followUpMsgId });
      onEvent({ type: 'STATE_DELTA', patch: { chips: answer.chips } });
      onEvent({ type: 'RUN_FINISHED', runId });
    } catch {
      if (!cancelled) onEvent({ type: 'RUN_ERROR', runId, message: 'The run could not finish.' });
    }
  })();

  return {
    done,
    cancel: () => {
      cancelled = true;
      cancelHooks.forEach((h) => h());
    },
  };
}

/** The "Explain" chip's follow-on: one more assistant message, no further question. */
export function runExplainFixture(explain: string, onEvent: NuraEventListener) {
  let cancelled = false;
  const runId = `run_${++runCounter}`;
  const cancelHooks: Array<() => void> = [];
  const wait = (ms: number) =>
    new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => (cancelled ? reject(new Error('cancelled')) : resolve()), ms);
      cancelHooks.push(() => clearTimeout(t));
    });

  const done = (async () => {
    try {
      onEvent({ type: 'RUN_STARTED', runId, intent: 'answer_question' });
      await wait(thinkHold * 0.6);
      if (cancelled) return;
      const msgId = `msg_${++messageCounter}`;
      onEvent({ type: 'TEXT_MESSAGE_START', messageId: msgId, role: 'assistant' });
      for (const word of chunk(explain)) {
        if (cancelled) return;
        onEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: msgId, delta: word });
        await wait(streamBody);
      }
      onEvent({ type: 'TEXT_MESSAGE_END', messageId: msgId });
      onEvent({ type: 'RUN_FINISHED', runId });
    } catch {
      if (!cancelled) onEvent({ type: 'RUN_ERROR', runId, message: 'The run could not finish.' });
    }
  })();

  return { done, cancel: () => { cancelled = true; cancelHooks.forEach((h) => h()); } };
}
