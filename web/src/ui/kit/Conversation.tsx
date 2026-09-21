import type { ComponentChildren, JSX } from "preact";
import { Chip, ChipRow } from "./Chip";
import { Icon } from "./icons";
import { StatusLine } from "./StatusLine";

/** Conversation, waiting and "thinking" (docs/design-direction.md), drawn as the approved board's
 *  Ask Nura screen draws them (docs/design/nura-concept-board.html): his question as a Plum
 *  bubble; while Nura works, a card with pulsing dots and "Nura is looking", each step done with a
 *  green tick or in progress with a turning ring; then Nura's answer as a card bubble with its
 *  source chips, the boundary line, and "What Nura looked at", which opens to the steps.
 *
 *  They are honest by construction. They draw what they are given, as it arrives: a step is on
 *  screen because the caller got it from the backend, never because a component made one up; an
 *  answer that is there is shown, never held back to let an animation finish. None of them keeps
 *  a timer. None of them uses a hook, so each renders the same on every call. */

/** One message, chat-style: his on the right in Plum, Nura's on the left on a card. */
export function MessageBubble({ from, children, label, testId }: { from: "person" | "nura"; children: ComponentChildren; label?: string; testId?: string }): JSX.Element {
  return (
    <div class="bubble" data-from={from} data-testid={testId}>
      {label && <span class="sr-only">{label}</span>}
      {children}
    </div>
  );
}

/** Nura is working: pulsing dots beside ONE status line, replaced in place with a light sweep as
 *  the real line changes (`StatusLine`, docs/design/experience-blueprint.html `.status`). `mark`:
 *  the seam for the brand mark's speaking motion (#176) — pass it and it stands where the dots
 *  do. With Reduce Motion the dots are still and the line swaps at once. The dots are decorative;
 *  the line is the words. */
export function ThinkingIndicator({ line, mark, testId }: { line: string; mark?: ComponentChildren; testId?: string }): JSX.Element {
  return (
    <div class="thinking" data-testid={testId}>
      <span class="thinking-mark" aria-hidden="true">
        {mark ?? (
          <span class="thinking-dots">
            <i />
            <i />
            <i />
          </span>
        )}
      </span>
      <StatusLine text={line} className="thinking-line" />
    </div>
  );
}

export interface TraceStep {
  /** The backend's own key for the step, so a step that ticks over to done stays the same row. */
  key: string;
  /** The backend's line, in plain words: "Reading your medicines". */
  text: string;
  done: boolean;
}

/** The steps, each done (a green tick) or in progress (a turning ring). */
export function TraceSteps({ steps }: { steps: readonly TraceStep[] }): JSX.Element {
  return (
    <ol class="trace-steps">
      {steps.map((step) => (
        <li key={step.key} class="trace-step" data-done={step.done ? "true" : "false"}>
          <span class={step.done ? "trace-tick" : "trace-spin"} aria-hidden="true">
            {step.done && <Icon name="check" />}
          </span>
          <span class="trace-text">{step.text}</span>
        </li>
      ))}
    </ol>
  );
}

/** The trace while Nura works: ONE line, the newest real step it has reported (or `working`
 *  before the first one arrives), replaced in place through `StatusLine` — never an accumulating
 *  checklist (docs/design/experience-blueprint.html `think()`: "thinking is ONE status line that
 *  changes in place with a light sweep. It is never an accumulating checklist."). Steps stay
 *  exactly what the backend sent: this never adds, reorders or delays one — `steps[steps.length -
 *  1]` is simply the latest one the caller was given. The full history still exists for "What
 *  Nura looked at" afterwards (`LookedAt`, below, still uses `TraceSteps`), just not here, live. */
export function StepTrace({ steps, working, mark, testId }: { steps: readonly TraceStep[]; working: string; mark?: ComponentChildren; testId?: string }): JSX.Element {
  const current = steps.length > 0 ? steps[steps.length - 1]!.text : working;
  return (
    <div class="trace" data-testid={testId}>
      <ThinkingIndicator line={current} mark={mark} testId="thinking" />
    </div>
  );
}

/** "What Nura looked at", under an answer: one line naming the parts of his papers it read (the
 *  backend's names, under the key's scope), which opens to the steps. Native `<details>`: a tap,
 *  Enter or Space opens it, and it says whether it is open. */
export function LookedAt({ summary, steps, testId }: { summary: string; steps: readonly TraceStep[]; testId?: string }): JSX.Element {
  return (
    <details class="looked" data-testid={testId}>
      <summary>
        <Icon name="check" />
        <span>{summary}</span>
      </summary>
      {steps.length > 0 && <TraceSteps steps={steps} />}
    </details>
  );
}

export type ExchangeStatus = "working" | "answered" | "slow" | "failed";

export interface ExchangeWords {
  /** Who each bubble is from, for the screen reader: "You asked", "Nura said". */
  you: string;
  nura: string;
  /** The line beside the dots, and the one announcement when Nura starts. */
  working: string;
  /** The one announcement when the answer is there. */
  answered: string;
  /** "What Nura looked at". */
  lookedAt: string;
  slow: string;
  failed: string;
  tryAgain: string;
}

interface ExchangeProps {
  question: string;
  steps: readonly TraceStep[];
  status: ExchangeStatus;
  /** Nura's answer, when it is there: shown the moment it is given, whatever the status says. */
  answer?: ComponentChildren;
  /** The parts of his papers the answer rests on, as chips under it ("Medicines", "Visit, 2 Sep").
   *  Required — pass `[]` when the answer cites nothing — so a caller cannot forget to think
   *  about what it rests on; an empty list is a choice, not an omission. */
  sources: readonly string[];
  /** The boundary line under the answer, in the backend's words ("Nura does not decide what is
   *  wrong."). Required, and never empty in practice: an answer with no boundary line is not
   *  drawn at all (see `answered` below), so a caller cannot show medical-adjacent content
   *  without it. */
  boundary: readonly string[];
  /** The one line under the answer: "What Nura looked at: medicines, visits", filled by the caller
   *  from what the backend says it read. Defaults to `words.lookedAt`. */
  lookedAt?: string;
  words: ExchangeWords;
  onRetry?: () => void;
  /** The brand mark's speaking motion, when #176 has it, in place of the dots. */
  mark?: ComponentChildren;
  testId?: string;
}

/** One question and its answer. The screen reader hears two things through the polite live
 *  region — that Nura started, and that the answer is there (or that it failed) — never each
 *  step, never a frame. A long wait or a failure is said plainly, with Try again. */
export function Exchange({ question, steps, status, answer, sources, boundary, lookedAt, words, onRetry, mark, testId }: ExchangeProps): JSX.Element {
  // "Answered" is the answer being there AND its boundary line being there, never a status
  // alone: with no answer given, or an answer with no boundary line under it, Nura is still
  // working, and nothing says it has answered. An answer never renders without a boundary line.
  const answered = answer !== undefined && answer !== null && boundary.length > 0;
  const shown: ExchangeStatus = answered ? "answered" : status === "answered" ? "working" : status;
  const announce = shown === "answered" ? words.answered : shown === "failed" ? words.failed : words.working;
  return (
    <section class="exchange" data-status={shown} data-testid={testId}>
      <MessageBubble from="person" label={words.you}>
        <p>{question}</p>
      </MessageBubble>
      {(shown === "working" || shown === "slow") && <StepTrace steps={steps} working={words.working} mark={mark} testId="trace" />}
      {shown === "slow" && (
        <div class="exchange-note" data-testid="exchange-slow">
          <p>{words.slow}</p>
          {onRetry && (
            <button type="button" class="pill compact" onClick={onRetry} data-testid="exchange-retry">
              {words.tryAgain}
            </button>
          )}
        </div>
      )}
      {shown === "failed" && (
        <div class="exchange-note" role="alert" data-testid="exchange-failed">
          <p>{words.failed}</p>
          {onRetry && (
            <button type="button" class="pill compact" onClick={onRetry} data-testid="exchange-retry">
              {words.tryAgain}
            </button>
          )}
        </div>
      )}
      {answered && (
        <MessageBubble from="nura" label={words.nura} testId="exchange-answer">
          <div class="answer-body">{answer}</div>
          {sources.length > 0 && (
            <ChipRow testId="answer-sources">
              {sources.map((source) => (
                <Chip key={source} testId="answer-source">
                  {source}
                </Chip>
              ))}
            </ChipRow>
          )}
          {boundary.length > 0 && (
            <div class="answer-boundary" data-testid="answer-boundary">
              {boundary.map((line, at) => (
                <p key={at}>{line}</p>
              ))}
            </div>
          )}
          <LookedAt summary={lookedAt ?? words.lookedAt} steps={steps} testId="trace" />
        </MessageBubble>
      )}
      <p class="sr-only" aria-live="polite" data-testid="exchange-live">
        {announce}
      </p>
    </section>
  );
}

/** A skeleton: a soft shimmering placeholder in a card's own shape, where a screen's content is
 *  still coming — never a spinner on a blank page. Hidden from the screen reader (the screen's
 *  own busy state speaks for it); with Reduce Motion it does not shimmer. */
export function SkeletonCard({ shape = "card", lines = 3, testId }: { shape?: "card" | "tile" | "row"; lines?: number; testId?: string }): JSX.Element {
  return (
    <div class="skeleton" data-shape={shape} aria-hidden="true" data-testid={testId}>
      {shape !== "row" && <span class="skeleton-bar title" />}
      {Array.from({ length: lines }, (_, at) => (
        <span key={at} class="skeleton-bar" style={{ width: `${92 - at * 14}%` }} />
      ))}
    </div>
  );
}
