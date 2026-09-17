import type { ComponentChildren, JSX } from "preact";
import { Icon } from "./icons";

/** A message in the ask thread (docs/design-direction.md "Conversation, waiting and
 *  thinking"; docs/design/nura-concept-board.html screen 5 — the approved visual target):
 *  his question as his own plum bubble, Nura's answer as a paper one on the other side.
 *
 *  LOCAL STAND-IN: the foundation builder is building a shared message bubble in
 *  `web/src/ui/kit`; once it lands on main, swap this for it rather than keeping two. */
export function MessageBubble({
  from,
  children,
  testId,
}: {
  from: "me" | "nura";
  children: ComponentChildren;
  testId?: string;
}): JSX.Element {
  return (
    <div class={`ask-bubble ${from}`} data-testid={testId}>
      {children}
    </div>
  );
}

/** The parts of his record an answer rests on, as small chips under it ("Medicines",
 *  "Visit, 2 Sep") — the same ids `AnswerLineOut.cites` and `withheld` name, never free text. */
export function SourceChips({ labels, testId }: { labels: readonly string[]; testId?: string }): JSX.Element | null {
  if (labels.length === 0) return null;
  return (
    <div class="ask-sources" data-testid={testId ?? "ask-sources"}>
      {labels.map((label, at) => (
        <span key={at} class="ask-source">
          {label}
        </span>
      ))}
    </div>
  );
}

/** "What Nura looked at": the trace collapsed to one line once the answer has arrived, naming
 *  only the parts this key's scope opened — never a part it did not read (spec, and
 *  `backend/app/search/ask.py`'s `STEP_KEYS`, which only ever yields a step for a part it
 *  actually read). */
export function LookedAt({ label, testId }: { label: string; testId?: string }): JSX.Element {
  return (
    <div class="ask-looked" data-testid={testId ?? "ask-looked"}>
      <Icon name="check" />
      {label}
    </div>
  );
}

/** One step of the trace: a plain line of what Nura is really doing, right now, or already
 *  did. Never invented, never scripted — each is a step event the backend streamed the
 *  instant that real read finished (`recall_stream`, `find_stream`). */
export function TraceStep({ label, done, testId }: { label: string; done: boolean; testId?: string }): JSX.Element {
  return (
    <div class={`ask-step${done ? " done" : ""}`} data-testid={testId}>
      {done ? (
        <span class="ask-step-tick" aria-hidden="true">
          <Icon name="check" />
        </span>
      ) : (
        <span class="ask-step-spin" aria-hidden="true" />
      )}
      {label}
    </div>
  );
}

/** The trace itself while an answer is still streaming: "Nura is looking", the pulsing dots
 *  (a static dot under `prefers-reduced-motion`, in CSS), and every step heard so far — the
 *  latest one still spinning, every one before it ticked.
 *
 *  Carries no `aria-live` of its own: a screen reader must hear that Nura started and that the
 *  answer is there, never a line every time a step ticks over — so the one announcement is the
 *  caller's own `aria-live="polite"` region, made once when the question is sent, not this
 *  element's changing content (spec 'Conversation, waiting and thinking'). */
export function ThinkingTrace({
  heading,
  steps,
  testId,
}: {
  heading: string;
  steps: readonly { key: string; label: string }[];
  testId?: string;
}): JSX.Element {
  return (
    <div class="ask-trace" data-testid={testId ?? "ask-trace"}>
      <div class="ask-trace-head">
        <span class="ask-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        {heading}
      </div>
      {steps.map((step, at) => (
        <TraceStep key={step.key} label={step.label} done={at < steps.length - 1} testId={`ask-step-${step.key}`} />
      ))}
    </div>
  );
}
