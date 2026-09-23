import { canSubmitReport, buildConfirmDecisions, unansweredFields, fieldNeedsAnswer } from '../confirmLogic';
import type { ReviewCard, ReviewField } from '../../../domain/reviewCard';

function field(overrides: Partial<ReviewField>): ReviewField {
  return {
    fieldId: 'f1',
    position: 0,
    subject: 'blood',
    attribute: 'LDL',
    value: 4.0,
    unit: 'mmol/L',
    confidence: 0.9,
    needsConfirm: false,
    unreadable: false,
    prompt: null,
    page: 1,
    range: null,
    labelOnPaper: null,
    state: 'proposed',
    correctedValue: null,
    correctedByPersonId: null,
    factId: null,
    ...overrides,
  };
}

function card(fields: ReviewField[]): ReviewCard {
  return {
    cardId: 'c1',
    profileId: 'p1',
    artifactId: 'a1',
    documentKind: 'lab_report',
    documentDate: null,
    askedAs: null,
    source: null,
    notice: null,
    highRiskClass: null,
    createdAt: '2026-01-01T00:00:00Z',
    confirmedAt: null,
    confirmedByPersonId: null,
    fields,
    clarify: null,
    discarded: false,
    duplicateOfAddedOn: null,
  };
}

describe('B4 — report table never defaults an unanswered flagged field to confirmed', () => {
  test('a needsConfirm field with no decision blocks submit', () => {
    const c = card([field({ fieldId: 'f1', needsConfirm: true })]);
    expect(canSubmitReport(c, {})).toBe(false);
    expect(unansweredFields(c, {})).toHaveLength(1);
    expect(() => buildConfirmDecisions(c, {})).toThrow();
  });

  test('answering the flagged field unblocks submit and is carried through unchanged', () => {
    const c = card([field({ fieldId: 'f1', needsConfirm: true })]);
    const decisions = { f1: 'rejected' as const };
    expect(canSubmitReport(c, decisions)).toBe(true);
    const out = buildConfirmDecisions(c, decisions);
    expect(out).toEqual([{ fieldId: 'f1', decision: 'rejected', correctedValue: null }]);
  });

  test('an untouched, never-flagged field defaults to confirmed only at submit, never in the decisions map itself', () => {
    const c = card([field({ fieldId: 'f1', needsConfirm: false })]);
    expect(canSubmitReport(c, {})).toBe(true); // nothing flagged, nothing to answer
    expect(fieldNeedsAnswer(c.fields[0], {})).toBe(false);
    const out = buildConfirmDecisions(c, {});
    expect(out).toEqual([{ fieldId: 'f1', decision: 'confirmed' }]);
  });

  test('a field already settled server-side (state != proposed) is never re-asserted, flagged or not', () => {
    const c = card([field({ fieldId: 'f1', needsConfirm: true, state: 'confirmed' })]);
    expect(canSubmitReport(c, {})).toBe(true); // already settled — no answer owed here
    expect(buildConfirmDecisions(c, {})).toEqual([]); // left out entirely, not re-sent as 'confirmed'
  });

  test('mixed table: one flagged-unanswered blocks even when others are fine', () => {
    const c = card([
      field({ fieldId: 'f1', needsConfirm: true }),
      field({ fieldId: 'f2', needsConfirm: true }),
      field({ fieldId: 'f3', needsConfirm: false }),
    ]);
    expect(canSubmitReport(c, { f1: 'confirmed' })).toBe(false);
    expect(unansweredFields(c, { f1: 'confirmed' }).map((f) => f.fieldId)).toEqual(['f2']);
    expect(canSubmitReport(c, { f1: 'confirmed', f2: 'confirmed' })).toBe(true);
  });
});
