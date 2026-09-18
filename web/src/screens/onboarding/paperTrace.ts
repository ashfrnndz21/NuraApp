import { useState } from "preact/hooks";
import type { TraceStep } from "../../ui/kit";

/** One paper's own real trace while Nura reads it (docs/design-direction.md 'Conversation,
 *  waiting and thinking'): each step is the backend's own word for a stage it just finished
 *  (`POST /imports/stream`, `/photos/stream`), oldest first — the same trace the many-photos
 *  batch shows (`PaperBatch.trace`). Nothing here invents a step or a delay; a file past the
 *  size cap goes the plain way with no steps, and the working line alone stands. */
export function usePaperTrace(): { trace: TraceStep[]; sending: boolean; start: () => void; stop: () => void; onStep: (key: string, text: string) => void } {
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [sending, setSending] = useState(false);
  return {
    trace,
    sending,
    start: () => {
      setTrace([]);
      setSending(true);
    },
    stop: () => setSending(false),
    onStep: (key, text) => setTrace((steps) => [...steps.map((step) => ({ ...step, done: true })), { key, text, done: false }]),
  };
}
