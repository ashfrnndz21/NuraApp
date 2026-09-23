import { saidDate, paperDate, fieldValueDate, displayFieldValue } from '../dates';

describe('saidDate (en) — the weekday and the date, no comma, no year (plain-words rule 5)', () => {
  test('2026-09-05 is a Saturday', () => {
    expect(saidDate('2026-09-05')).toBe('Saturday 5 September');
  });

  test('never an ISO string and never a comma', () => {
    const s = saidDate('2026-01-01');
    expect(s).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(s).not.toContain(',');
  });

  test('never the year', () => {
    expect(saidDate('2026-09-05')).not.toMatch(/2026/);
  });

  test('reads the calendar day as local midnight, not UTC (no off-by-one)', () => {
    // A date at UTC midnight parsed naively can roll back a day west of UTC — saidDate must
    // not do that: the 1st stays the 1st.
    expect(saidDate('2026-03-01')).toBe('Sunday 1 March');
  });
});

describe('paperDate (en) — carries its own year, weekday still first', () => {
  test('2026-09-05', () => {
    expect(paperDate('2026-09-05')).toBe('Saturday, 5 September 2026');
  });
});

describe('fieldValueDate — a report row VALUE read as a date, never the raw ISO string (third independent review of PR #332)', () => {
  test('a bare date value', () => {
    expect(fieldValueDate('2026-08-20')).toBe('20 August 2026');
  });

  test('a date value carrying a clock time', () => {
    expect(fieldValueDate('2025-01-21T21:16')).toBe('21 January 2025, 9:16 pm');
  });

  test('not a date at all — null, left to the caller, never guessed', () => {
    expect(fieldValueDate('6.1')).toBeNull();
    expect(fieldValueDate('Sunrise Medical Laboratory')).toBeNull();
  });

  test('an impossible calendar day is left alone, not rolled over silently', () => {
    expect(fieldValueDate('2025-02-30')).toBeNull();
  });
});

describe('displayFieldValue — a report row value, worded when it is a date', () => {
  test('a numeric result passes through untouched', () => {
    expect(displayFieldValue(6.1)).toBe('6.1');
  });
  test('a plain text value passes through untouched', () => {
    expect(displayFieldValue('Sunrise Medical Laboratory')).toBe('Sunrise Medical Laboratory');
  });
  test('a date-shaped string value is worded, never the raw ISO string', () => {
    expect(displayFieldValue('2026-08-20')).toBe('20 August 2026');
    expect(displayFieldValue('2026-08-20')).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });
  test('null/undefined renders the honest em dash, never "null"/"undefined"', () => {
    expect(displayFieldValue(null)).toBe('—');
    expect(displayFieldValue(undefined)).toBe('—');
  });
});
