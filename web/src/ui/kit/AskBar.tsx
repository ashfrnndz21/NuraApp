import type { ComponentChildren, JSX, Ref } from "preact";
import { Icon } from "./icons";

export interface AskBarProps {
  value: string;
  /** "Ask or search", "Ask about Pa". */
  placeholder: string;
  /** The field's name for the screen reader: "Your question". */
  label: string;
  onInput: (value: string) => void;
  onSubmit: () => void;
  /** The voice button. Absent, there is only typing. */
  onVoice?: () => void;
  voiceLabel: string;
  submitLabel: string;
  busy?: boolean;
  testId?: string;
  inputRef?: Ref<HTMLInputElement>;
  /** Under the bar: the filters (Records, Web, Providers, Videos) as chips, when a screen has them. */
  children?: ComponentChildren;
}

/** Ask or search (docs/ui-mockup-v2.html): a paper pill with the search icon, the field, and one
 *  button at the end — the voice button while the field is empty, "Ask" once there are words.
 *  Enter asks too. The voice button never listens itself: the screen decides what voice means. */
export function AskBar({ value, placeholder, label, onInput, onSubmit, onVoice, voiceLabel, submitLabel, busy, testId, inputRef, children }: AskBarProps): JSX.Element {
  const typed = value.trim().length > 0;
  return (
    <div class="ask" data-testid={testId ?? "askbar"}>
      <form
        class="askbar"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (typed && !busy) onSubmit();
        }}
      >
        <label class="askbar-field">
          <Icon name="search" />
          <span class="sr-only">{label}</span>
          <input
            ref={inputRef}
            type="search"
            name="ask"
            enterKeyHint="search"
            autoComplete="off"
            placeholder={placeholder}
            value={value}
            maxLength={300}
            onInput={(event) => onInput((event.target as HTMLInputElement).value)}
            data-testid="ask-input"
          />
        </label>
        {typed ? (
          <button type="submit" class="askbar-go" disabled={busy} data-testid="ask-go">
            <span>{submitLabel}</span>
          </button>
        ) : (
          onVoice && (
            <button type="button" class="askbar-voice" onClick={onVoice} data-testid="ask-voice">
              <Icon name="mic" />
              <span>{voiceLabel}</span>
            </button>
          )
        )}
      </form>
      {children && <div class="chip-row ask-filters">{children}</div>}
    </div>
  );
}
