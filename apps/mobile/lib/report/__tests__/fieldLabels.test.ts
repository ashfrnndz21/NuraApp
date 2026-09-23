import { fieldLabel, isResultRow, kindTitle } from '../fieldLabels';
import type { DocumentKind } from '../../../domain/reviewCard';

const SNAKE_CASE = /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/;

describe('fieldLabel — never the raw subject/attribute token (section 29, no raw token on screen)', () => {
  const cases: { subject: string; attribute: string; labelOnPaper: string | null }[] = [
    { subject: 'lab_report', attribute: 'facility', labelOnPaper: null },
    { subject: 'lipid_panel', attribute: 'total_cholesterol', labelOnPaper: 'Total Cholesterol' },
    { subject: 'lipid_panel', attribute: 'ldl', labelOnPaper: 'LDL Cholesterol' },
    { subject: 'lipid_panel', attribute: 'hdl', labelOnPaper: 'HDL Cholesterol' },
    { subject: 'lipid_panel', attribute: 'triglycerides', labelOnPaper: 'Triglycerides' },
    { subject: 'blood_sugar', attribute: 'glucose', labelOnPaper: 'Fasting Glucose' },
    { subject: 'kidney_panel', attribute: 'potassium', labelOnPaper: 'Potassium (K+)' },
    { subject: 'blood_test', attribute: 'haemoglobin', labelOnPaper: 'Haemoglobin (Hb)' },
    { subject: 'insurance_policy', attribute: 'covers_1', labelOnPaper: null },
    { subject: 'item_3', attribute: 'name', labelOnPaper: null },
  ];

  test.each(cases)('$subject.$attribute never renders as a snake_case token', ({ subject, attribute, labelOnPaper }) => {
    const label = fieldLabel({ subject, attribute, labelOnPaper });
    expect(label).not.toMatch(SNAKE_CASE);
    expect(label).not.toBe(subject);
    expect(label).not.toBe(attribute);
    expect(label.length).toBeGreaterThan(0);
  });

  test('an unknown field falls back to the printed label, not the code', () => {
    expect(fieldLabel({ subject: 'made_up_subject', attribute: 'made_up_attribute', labelOnPaper: 'What The Paper Says' })).toBe(
      'What The Paper Says',
    );
  });

  test('an unknown field with no printed label falls back to the generic line, not the code', () => {
    const label = fieldLabel({ subject: 'made_up_subject', attribute: 'made_up_attribute', labelOnPaper: null });
    expect(label).not.toMatch(SNAKE_CASE);
    expect(label).toBe('Another line on the paper');
  });
});

describe('isResultRow — a result row has a unit or a printed range; an admin row has neither', () => {
  test('facility (no unit, no range) is an admin row', () => {
    expect(isResultRow({ unit: null, range: null })).toBe(false);
  });
  test('a lab value with a unit and a range is a result row', () => {
    expect(isResultRow({ unit: 'mmol/L', range: { low: null, high: 5.2, text: '<5.2' } })).toBe(true);
  });
  test('a value with only a unit (no range parsed) is still a result row', () => {
    expect(isResultRow({ unit: 'mmol/L', range: null })).toBe(true);
  });
});

describe('kindTitle — a short name, never the raw document_kind token', () => {
  const kinds: DocumentKind[] = [
    'lab_report',
    'medicine_label',
    'discharge_letter',
    'clinic_slip',
    'handwritten_prescription',
    'insurance_letter',
    'insurance_policy',
    'insurance_claim',
    'device_screen',
    'pill_photo',
    'pharmacy_receipt',
    'other',
    'not_health',
    'unknown',
    'unsupported_file_type',
  ];

  test.each(kinds)('%s never renders as its own raw token', (kind) => {
    const title = kindTitle(kind);
    expect(title).not.toBe(kind);
    expect(title).not.toMatch(SNAKE_CASE);
  });

  test('lab_report reads "Blood test"', () => {
    expect(kindTitle('lab_report')).toBe('Blood test');
  });
});
