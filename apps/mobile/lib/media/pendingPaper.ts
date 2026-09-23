import type { ReviewCard } from '../../domain/reviewCard';

/**
 * The paper(s) just picked on `add-paper.tsx`, held in memory for
 * `reading.tsx` to read — a base64 photo/PDF is too large to pass as a
 * router param. One screen sets it, the very next screen consumes and
 * clears it; never persisted, never held past one paper's own run.
 */
export interface PendingPaper {
  data: string;
  contentType: string;
  capturedAt: string;
  label: string;
}

let queue: PendingPaper[] = [];

export function setPendingPapers(papers: PendingPaper[]): void {
  queue = papers;
}

export function takeNextPendingPaper(): PendingPaper | null {
  const next = queue.shift() ?? null;
  return next;
}

export function pendingPaperCount(): number {
  return queue.length;
}

/**
 * Every card `reading.tsx` has finished this session, held for
 * `report.tsx` — the very next screen — the same short-lived, in-memory
 * pattern as the paper queue above (never persisted, never read by
 * anything else).
 *
 * B5, independent review of PR #332: for N photos picked at once,
 * `reading.tsx` used to overwrite a single "last card" slot per paper —
 * so N-1 of N cards were read by the backend but never shown or
 * confirmed on screen. This is a queue, appended to, never overwritten,
 * so `report.tsx` can walk every paper's own table (section 22).
 */
let reviewCardQueue: ReviewCard[] = [];

export function addFinishedReviewCard(card: ReviewCard): void {
  reviewCardQueue = [...reviewCardQueue, card];
}

export function getReviewCardQueue(): ReviewCard[] {
  return reviewCardQueue;
}

export function clearReviewCardQueue(): void {
  reviewCardQueue = [];
}

/** Replaces one card in the queue with its updated self (after a confirm/answer call). */
export function updateReviewCardInQueue(updated: ReviewCard): void {
  reviewCardQueue = reviewCardQueue.map((c) => (c.cardId === updated.cardId ? updated : c));
}
