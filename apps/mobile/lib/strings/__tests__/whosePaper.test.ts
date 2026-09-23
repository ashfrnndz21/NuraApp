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
  test('names the date when given one', () => {
    expect(duplicateLead('12 September')).toBe('This looks like the paper you added on 12 September.');
  });

  test('falls back honestly when there is no date', () => {
    expect(duplicateLead(null)).toBe('This looks like a paper you already have.');
  });
});
