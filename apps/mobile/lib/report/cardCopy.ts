/**
 * Pure copy helpers for the report table (BL-1, second independent
 * review of PR #332; the raw-token/ISO-date fix, third review) — kept
 * out of `report.tsx` so they're unit testable without rendering.
 */
import type { ReviewCard } from '../../domain/reviewCard';
import { kindTitle } from './fieldLabels';
import { saidDate } from '../dates';

/**
 * The card's own kicker line — the worded date, the source, the kind's
 * short title — joined with " · " between only the parts that actually
 * exist. Patient-visible defect (third independent review of PR #332):
 * this used to print `card.documentDate` verbatim (an ISO string,
 * "2026-09-05") and a hand-rolled kind word — now `saidDate` (plain-
 * words rule 5: the weekday and the date, no comma, no year) and
 * `kindTitle` (the same catalogue `web/src/onboarding/review.ts` reads).
 */
export function reportKickerLine(card: Pick<ReviewCard, 'documentDate' | 'source' | 'documentKind'>): string {
  const parts = [
    card.documentDate ? saidDate(card.documentDate) : null,
    card.source,
    kindTitle(card.documentKind),
  ].filter((p): p is string => Boolean(p && p.length > 0));
  return parts.join(' · ');
}

/** Whether this card found nothing to show a table for at all. */
export function hasNoFields(card: Pick<ReviewCard, 'fields'>): boolean {
  return card.fields.length === 0;
}
