import { reportKickerLine, hasNoFields } from '../cardCopy';

describe('reportKickerLine — never a dangling "·" when a part is missing', () => {
  test('all parts present', () => {
    expect(reportKickerLine({ documentDate: '12 September', source: 'portal', documentKind: 'lab_report' })).toBe(
      '12 September · portal · lab report',
    );
  });

  test('date missing', () => {
    expect(reportKickerLine({ documentDate: null, source: 'portal', documentKind: 'lab_report' })).toBe(
      'portal · lab report',
    );
  });

  test('date and source both missing', () => {
    expect(reportKickerLine({ documentDate: null, source: null, documentKind: 'lab_report' })).toBe('lab report');
    expect(reportKickerLine({ documentDate: null, source: null, documentKind: 'lab_report' })).not.toMatch(/^\s*·/);
  });

  test('unknown document kind still renders something readable', () => {
    // @ts-expect-error - deliberately an unmapped value, to check the fallback
    expect(reportKickerLine({ documentDate: null, source: null, documentKind: 'something_new' })).toBe('something_new');
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
