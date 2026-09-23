/**
 * Pure copy helpers for the report table (BL-1, second independent
 * review of PR #332) — kept out of `report.tsx` so they're unit
 * testable without rendering.
 */
import type { ReviewCard } from '../../domain/reviewCard';

export const DOCUMENT_KIND_WORD: Record<string, string> = {
  lab_report: 'lab report',
  medicine_label: 'medicine label',
  discharge_letter: 'discharge letter',
  clinic_slip: 'clinic slip',
  handwritten_prescription: 'handwritten prescription',
  insurance_letter: 'insurance letter',
  insurance_policy: 'insurance policy',
  insurance_claim: 'insurance claim',
  device_screen: 'device screen',
  pill_photo: 'pill photo',
  pharmacy_receipt: 'pharmacy receipt',
  other: 'paper',
  not_health: 'paper',
  unknown: 'paper',
  unsupported_file_type: 'file',
};

/**
 * The card's own kicker line — date, source, document kind — joined with
 * " · " between only the parts that actually exist. Previously always
 * emitted the source/kind separators even when `documentDate`/`source`
 * were null, leaving a dangling "·" with nothing before it.
 */
export function reportKickerLine(card: Pick<ReviewCard, 'documentDate' | 'source' | 'documentKind'>): string {
  const parts = [
    card.documentDate,
    card.source,
    DOCUMENT_KIND_WORD[card.documentKind] ?? card.documentKind,
  ].filter((p): p is string => Boolean(p && p.length > 0));
  return parts.join(' · ');
}

/** Whether this card found nothing to show a table for at all. */
export function hasNoFields(card: Pick<ReviewCard, 'fields'>): boolean {
  return card.fields.length === 0;
}
