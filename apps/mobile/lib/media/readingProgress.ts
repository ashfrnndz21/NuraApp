/**
 * The "Paper X of N" shared-status line (BL-2, second independent
 * review of PR #332) — pure and testable apart from `reading.tsx`'s own
 * render. `remainingAfterDequeue` is `pendingPaperCount()` read *after*
 * the current paper has already been taken off the queue (the earlier
 * bug read it before, double-counting the current paper: one paper
 * produced "Paper 2 of 2").
 */
export function readingProgressPosition(total: number, remainingAfterDequeue: number): number {
  return total - remainingAfterDequeue;
}

/** `null` suppresses the counter entirely — a single paper never shows "Paper 1 of 1". */
export function readingProgressLabel(total: number, remainingAfterDequeue: number): string | null {
  if (total <= 1) return null;
  return `Paper ${readingProgressPosition(total, remainingAfterDequeue)} of ${total}`;
}
