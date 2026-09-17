import type { ComponentChildren, JSX } from "preact";
import { Icon } from "./icons";

/** Conversation, waiting and "thinking" (docs/design-direction.md): the shared pieces every ask,
 *  search and message composer draws, so they all look and behave the same.
 *
 *  They are honest by construction. They draw what they are given, as it arrives: a step is on
 *  screen because the caller got it from the backend, never because a component made one up; an
 *  answer that is there is shown, never held back to let an animation finish. None of them keeps
 *  a timer. None of them uses a hook, so each renders the same on every call. */

/** One message, chat-style: his question on the right, Nura's answer on the left. */
export function MessageBubble({ from, children, label, testId }: { from: "person" | "nura"; children: ComponentChildren; label?: string; testId?: string }): JSX.Element {
  return (
    <div class="bubble" data-from={from} data-testid={testId}>
      {label && <span class="sr-only">{label}</span>}
      {children}
    </div>
  );
}

/** Nura is working: calm pulsing dots beside a plain line of what is happening. `mark`: the seam
 *  for the brand mark's speaking motion (#176) — pass it and it stands where the dots do. With
 *  Reduce Motion the dots are still. Decorative apart from the line, which is the words. */
export function ThinkingIndicator({ line, mark, testId }: { line: string; mark?: ComponentChildren; testId?: string }): JSX.Element {
  return (
    <div class="thinking" data-testid={testId}>
      <span class="thinking-mark" aria-hidden="true">
        {mark ?? (
          <span class="thinking-dots">
            <span />
            <span />
            <span />
          </span>
        )}
      </span>
      <span class="thinking-line">{line}</span>
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

/** The step trace: while Nura works, every step it has really taken, each in progress or done;
 *  once the answer is there, one line — "What Nura looked at" — that opens to the same steps.
 *  Native `<details>`: it opens with a tap, Enter or Space, and says whether it is open. */
export function StepTrace({ steps, answered, summary, testId }: { steps: readonly TraceStep[]; answered: boolean; summary: string; testId?: string }): JSX.Element | null {
  if (steps.length === 0) return null;
  const list = (
    <ol class="trace-steps">
      {steps.map((step) => (
        <li key={step.key} class="trace-step" data-done={step.done ? "true" : "false"}>
          <span class="trace-state" aria-hidden="true">
            {step.done ? <Icon name="check" /> : <span class="trace-pending" />}
          </span>
          <span class="trace-text">{step.text}</span>
        </li>
      ))}
    </ol>
  );
  if (!answered) {
    return (
      <div class="trace" data-testid={testId}>
        {list}
      </div>
    );
  }
  return (
    <details class="trace" data-testid={testId}>
      <summary class="trace-summary">{summary}</summary>
      {list}
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
  /** Nura's answer, when it is there: shown the moment it is given, whatever the steps say. */
  answer?: ComponentChildren;
  words: ExchangeWords;
  onRetry?: () => void;
  testId?: string;
}

/** One question and its answer: his question as his message; while Nura works, the dots and the
 *  steps so far; then the answer as Nura's message, with the steps folded into "What Nura looked
 *  at". A long wait or a failure is said plainly, with Try again.
 *
 *  The screen reader hears two things through the polite live region — that Nura started, and
 *  that the answer is there (or that it failed) — never each step, never a frame. */
export function Exchange({ question, steps, status, answer, words, onRetry, testId }: ExchangeProps): JSX.Element {
  const answered = answer !== undefined && answer !== null;
  const shown: ExchangeStatus = answered ? "answered" : status;
  const announce = shown === "answered" ? words.answered : shown === "failed" ? words.failed : words.working;
  return (
    <section class="exchange" data-status={shown} data-testid={testId}>
      <MessageBubble from="person" label={words.you}>
        <p>{question}</p>
      </MessageBubble>
      {(shown === "working" || shown === "slow") && <ThinkingIndicator line={words.working} testId="thinking" />}
      <StepTrace steps={steps} answered={shown === "answered"} summary={words.lookedAt} testId="trace" />
      {shown === "slow" && (
        <p class="exchange-note" data-testid="exchange-slow">
          {words.slow}
        </p>
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
      {shown === "slow" && onRetry && (
        <button type="button" class="pill compact" onClick={onRetry} data-testid="exchange-retry">
          {words.tryAgain}
        </button>
      )}
      {answered && (
        <MessageBubble from="nura" label={words.nura} testId="exchange-answer">
          {answer}
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
