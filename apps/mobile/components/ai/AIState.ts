/**
 * The AI state machine (mobile-architecture.md §3 / design-build-2.md §28):
 * idle → listening → thinking → responding → idle, * → error → idle.
 * Driven only by events from the stream (RUN_STARTED, TEXT_MESSAGE_*,
 * TOOL_CALL_*, RUN_FINISHED, RUN_ERROR) plus the composer's own
 * focus/voice for `listening`. Never a timer changes this on its own —
 * the demo's state changes come from the composer's real fixture
 * sequence (`lib/ai/events.ts`) or a live run, both the same shape.
 *
 * Every subscriber (the orb, the ambient background, cards, the
 * composer's status line) reads this one store.
 */
import { create } from 'zustand';

import type { NuraEvent } from '../../lib/ai/events';

export type AIStateName = 'idle' | 'listening' | 'thinking' | 'responding' | 'error';

interface AIStateStore {
  state: AIStateName;
  /** The one status line, changed in place (never "Loading…"). */
  statusLine: string | null;
  /** The latest assistant message, accumulated word by word as TEXT_MESSAGE_CONTENT arrives. */
  responseText: string;
  /** The latest user message, accumulated the same way while listening. */
  askedText: string;
  /** Chips offered after an answer (spec §10). */
  chips: string[];
  errorMessage: string | null;

  /** The composer calls this on focus/voice-start — the one place `listening` is set directly. */
  setListening: () => void;
  /** Returns the machine to idle and clears transient text — never mid-run. */
  reset: () => void;
  /** The only other way state changes: a real event off the stream. */
  consumeEvent: (event: NuraEvent) => void;
}

export const useAIState = create<AIStateStore>((set, get) => ({
  state: 'idle',
  statusLine: null,
  responseText: '',
  askedText: '',
  chips: [],
  errorMessage: null,

  setListening: () =>
    set({ state: 'listening', responseText: '', askedText: '', chips: [], errorMessage: null, statusLine: null }),

  reset: () => set({ state: 'idle', statusLine: null, responseText: '', askedText: '', chips: [], errorMessage: null }),

  consumeEvent: (event: NuraEvent) => {
    switch (event.type) {
      case 'RUN_STARTED':
        set({ errorMessage: null });
        return;
      case 'TEXT_MESSAGE_START':
        if (event.role === 'user') {
          set({ state: 'listening', askedText: '' });
        } else {
          set({ state: 'responding', responseText: '' });
        }
        return;
      case 'TEXT_MESSAGE_CONTENT': {
        const isUser = get().state === 'listening';
        if (isUser) {
          set((s) => ({ askedText: (s.askedText + event.delta).trimStart() }));
        } else {
          set((s) => ({ responseText: (s.responseText + event.delta).trimStart() }));
        }
        return;
      }
      case 'TEXT_MESSAGE_END':
        return;
      case 'TOOL_CALL_START':
        set({ state: 'thinking', statusLine: event.label });
        return;
      case 'TOOL_CALL_END':
      case 'TOOL_CALL_RESULT':
        return;
      case 'STATE_DELTA':
        if (Array.isArray(event.patch.chips)) {
          set({ chips: event.patch.chips as string[] });
        }
        return;
      case 'STATE_SNAPSHOT':
        return;
      case 'RUN_FINISHED':
        set({ state: 'idle', statusLine: null });
        return;
      case 'RUN_ERROR':
        set({ state: 'error', statusLine: null, errorMessage: event.message });
        return;
      default:
        return;
    }
  },
}));

/** Convenience selector — components that only need the state name re-render only on its change. */
export const useAIStateName = () => useAIState((s) => s.state);
