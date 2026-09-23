import { whoseMismatchLead, duplicateLead } from '../whosePaper';

describe('whoseMismatchLead — composed from the closed mismatched-field list only', () => {
  test('one field', () => {
    expect(whoseMismatchLead(['name'])).toBe('The name on this paper is not yours.');
  });

  test('two fields join with "and", verb becomes "are"', () => {
    expect(whoseMismatchLead(['name', 'birth_year'])).toBe(
      'The name and the year of birth on this paper are not yours.',
    );
  });

  test('never contains the paper’s own printed value — only closed field words', () => {
    const lead = whoseMismatchLead(['patient_id', 'sex']);
    expect(lead).toContain('patient number');
    expect(lead).toContain('the sex');
    expect(lead).not.toMatch(/\d{2,}/); // no leaked id/number
  });

  test('no mismatched fields falls back to the generic line', () => {
    expect(whoseMismatchLead([])).toBe('This paper’s details do not match your own.');
  });
});

describe('duplicateLead', () => {
  test('names the date when given one — worded, never the raw ISO string (third independent review of PR #332)', () => {
    expect(duplicateLead('2026-09-05')).toBe('This looks like the paper you added on Saturday 5 September.');
  });

  test('never the raw ISO date on screen', () => {
    expect(duplicateLead('2026-09-05')).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  test('falls back honestly when there is no date', () => {
    expect(duplicateLead(null)).toBe('This looks like a paper you already have.');
  });
});
