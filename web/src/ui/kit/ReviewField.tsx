import type { JSX } from "preact";

/** One field of a capture review card (docs/design-system.md §4): what was read, with its
 *  confidence as a soft underline — solid where Nura is sure, dotted where he should check it
 *  against the paper. The words and the value are the backend's. */
export function ReviewField({ label, value, unit, sure, testId }: { label: string; value: string; unit?: string | null; sure: boolean; testId?: string }): JSX.Element {
  return (
    <div class="review-field" data-sure={sure ? "true" : "false"} data-testid={testId}>
      <span class="review-label">{label}</span>
      <span class={sure ? "review-value sure" : "review-value check"}>
        {value}
        {unit && <span class="review-unit"> {unit}</span>}
      </span>
    </div>
  );
}
