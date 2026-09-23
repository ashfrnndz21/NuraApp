import { useAIState } from '../AIState';

const reset = () => useAIState.getState().reset();

beforeEach(reset);

describe('AIState reducer — driven only by events, never a timer', () => {
  test('idle -> listening: setListening is the one direct transition', () => {
    useAIState.getState().setListening();
    expect(useAIState.getState().state).toBe('listening');
  });

  test('TEXT_MESSAGE_START(role: assistant) -> responding, accumulates TEXT_MESSAGE_CONTENT', () => {
    const { consumeEvent } = useAIState.getState();
    consumeEvent({ type: 'RUN_STARTED', runId: 'r1', intent: 'answer_question' });
    consumeEvent({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' });
    expect(useAIState.getState().state).toBe('responding');
    consumeEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Your ' });
    consumeEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'blood pressure ' });
    expect(useAIState.getState().responseText).toBe('Your blood pressure ');
  });

  test('TEXT_MESSAGE_START(role: user) -> listening, accumulates askedText separately from responseText', () => {
    const { consumeEvent } = useAIState.getState();
    consumeEvent({ type: 'TEXT_MESSAGE_START', messageId: 'u1', role: 'user' });
    consumeEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'u1', delta: 'What does ' });
    consumeEvent({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'u1', delta: 'this mean' });
    expect(useAIState.getState().state).toBe('listening');
    expect(useAIState.getState().askedText).toBe('What does this mean');
    expect(useAIState.getState().responseText).toBe('');
  });

  test('TOOL_CALL_START -> thinking, statusLine is the stage word, never the tool name', () => {
    const { consumeEvent } = useAIState.getState();
    consumeEvent({ type: 'TOOL_CALL_START', toolCallId: 't1', toolName: 'read_own_record', label: 'Looking through your recent results' });
    expect(useAIState.getState().state).toBe('thinking');
    expect(useAIState.getState().statusLine).toBe('Looking through your recent results');
  });

  test('RUN_FINISHED -> idle, clears the status line', () => {
    const { consumeEvent } = useAIState.getState();
    consumeEvent({ type: 'TOOL_CALL_START', toolCallId: 't1', toolName: 'x', label: 'Reading' });
    consumeEvent({ type: 'RUN_FINISHED', runId: 'r1' });
    expect(useAIState.getState().state).toBe('idle');
    expect(useAIState.getState().statusLine).toBeNull();
  });

  test('RUN_ERROR -> error, carries the plain-words message', () => {
    const { consumeEvent } = useAIState.getState();
    consumeEvent({ type: 'RUN_ERROR', runId: 'r1', message: "We couldn't reach your clinic records right now." });
    expect(useAIState.getState().state).toBe('error');
    expect(useAIState.getState().errorMessage).toBe("We couldn't reach your clinic records right now.");
  });

  test('STATE_DELTA with chips updates the chips list without changing state', () => {
    const { consumeEvent } = useAIState.getState();
    consumeEvent({ type: 'RUN_STARTED', runId: 'r1', intent: 'answer_question' });
    consumeEvent({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' });
    consumeEvent({ type: 'STATE_DELTA', patch: { chips: ['Tell me more', 'Ask my doctor'] } });
    expect(useAIState.getState().chips).toEqual(['Tell me more', 'Ask my doctor']);
    expect(useAIState.getState().state).toBe('responding');
  });

  test('reset clears every transient field back to idle', () => {
    const { consumeEvent, reset: doReset } = useAIState.getState();
    consumeEvent({ type: 'TOOL_CALL_START', toolCallId: 't1', toolName: 'x', label: 'Reading' });
    consumeEvent({ type: 'STATE_DELTA', patch: { chips: ['a'] } });
    doReset();
    const s = useAIState.getState();
    expect(s).toMatchObject({
      state: 'idle',
      statusLine: null,
      responseText: '',
      askedText: '',
      chips: [],
      errorMessage: null,
    });
  });
});
