/**
 * The report table's own submit rule (B4, independent review of PR
 * #332): a field the screen flagged `needsConfirm` must have an
 * explicit person's answer before "Looks right" may fire at all — never
 * a silent `?? 'confirmed'` default standing in for a field nobody
 * actually looked at. `field.state` (the wire's own authoritative
 * marker, `ReviewFieldOut.state`) is checked first: a field the backend
 * already has as `confirmed`/`corrected`/`rejected` (settled by an
 * earlier partial confirm, say) needs no fresh answer here, whatever
 * this screen's own `decisions` map says.
 */
import type { ReviewCard, ReviewField, FieldDecision, FieldDecisionIn } from '../../domain/reviewCard';

/** Whether this field still needs the person's own explicit answer before submit may fire. */
export function fieldNeedsAnswer(field: ReviewField, decisions: Record<string, FieldDecision>): boolean {
  if (!field.needsConfirm) return false;
  if (field.state !== 'proposed') return false; // already settled server-side
  return decisions[field.fieldId] === undefined;
}

/** Every field still waiting on the person, in position order — for highlighting. */
export function unansweredFields(card: ReviewCard, decisions: Record<string, FieldDecision>): ReviewField[] {
  return card.fields.filter((f) => fieldNeedsAnswer(f, decisions)).sort((a, b) => a.position - b.position);
}

/** "Looks right" may only fire once every flagged, still-`proposed` field has an explicit decision. */
export function canSubmitReport(card: ReviewCard, decisions: Record<string, FieldDecision>): boolean {
  return unansweredFields(card, decisions).length === 0;
}

/**
 * The decisions to send on submit. A field the person answered keeps
 * that answer; a field already settled server-side (`state` is not
 * `proposed`) is left out entirely, never re-asserted; only an
 * untouched, never-flagged field is defaulted to `confirmed` here —
 * "Looks right"'s own meaning for the fields this screen never asked a
 * question about. Throws if a flagged, still-`proposed` field has no
 * answer — callers must gate on `canSubmitReport` first, this is the
 * safety net, not the check itself.
 */
export function buildConfirmDecisions(
  card: ReviewCard,
  decisions: Record<string, FieldDecision>,
): FieldDecisionIn[] {
  if (!canSubmitReport(card, decisions)) {
    throw new Error('buildConfirmDecisions: an unanswered flagged field remains — call canSubmitReport first');
  }
  const out: FieldDecisionIn[] = [];
  for (const field of card.fields) {
    if (field.state !== 'proposed') continue; // already settled — never re-asserted
    const decision = decisions[field.fieldId];
    if (decision !== undefined) {
      out.push({ fieldId: field.fieldId, decision, correctedValue: field.correctedValue });
    } else {
      // Not flagged, never answered, still proposed — "Looks right"'s own meaning.
      out.push({ fieldId: field.fieldId, decision: 'confirmed' });
    }
  }
  return out;
}
