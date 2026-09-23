import { reportKickerLine, hasNoFields } from '../cardCopy';

describe('reportKickerLine — never a dangling "·" when a part is missing, never a raw ISO date or document_kind token', () => {
  test('all parts present — the date is worded, the kind is its short title', () => {
    expect(reportKickerLine({ documentDate: '2026-09-05', source: 'portal', documentKind: 'lab_report' })).toBe(
      'Saturday 5 September · portal · Blood test',
    );
  });

  test('never the raw ISO date string on screen', () => {
    const line = reportKickerLine({ documentDate: '2026-09-05', source: null, documentKind: 'lab_report' });
    expect(line).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  test('never the raw document_kind token on screen', () => {
    const line = reportKickerLine({ documentDate: null, source: null, documentKind: 'lab_report' });
    expect(line).not.toBe('lab_report');
    expect(line).not.toMatch(/_/);
  });

  test('date missing', () => {
    expect(reportKickerLine({ documentDate: null, source: 'portal', documentKind: 'lab_report' })).toBe(
      'portal · Blood test',
    );
  });

  test('date and source both missing', () => {
    expect(reportKickerLine({ documentDate: null, source: null, documentKind: 'lab_report' })).toBe('Blood test');
    expect(reportKickerLine({ documentDate: null, source: null, documentKind: 'lab_report' })).not.toMatch(/^\s*·/);
  });
});

describe('hasNoFields', () => {
  test('true when the card has no fields at all', () => {
    expect(hasNoFields({ fields: [] })).toBe(true);
  });
  test('false otherwise', () => {
    expect(hasNoFields({ fields: [{} as never] })).toBe(false);
  });
});
