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
 * The card `reading.tsx` just finished, held for `report.tsx` — the very
 * next screen — the same short-lived, in-memory pattern as the paper
 * queue above (never persisted, never read by anything else).
 */
let lastCard: ReviewCard | null = null;

export function setLastReviewCard(card: ReviewCard | null): void {
  lastCard = card;
}

export function getLastReviewCard(): ReviewCard | null {
  return lastCard;
}
