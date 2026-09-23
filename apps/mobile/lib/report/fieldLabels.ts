/**
 * His words for a report row (patient-visible defect #1, third
 * independent review of PR #332): the report table was printing raw
 * backend tokens as labels (`facility`, `lipid_panel`, `blood_sugar`) —
 * section 29's own rule, never a raw token on screen. Ported from
 * `web/src/strings/en.ts`'s `onboarding.fields` catalogue and
 * `web/src/onboarding/review.ts`'s `fieldLabel`/`isResultRow`/`kindTitle`
 * — the same plain names the web client already uses, not invented
 * fresh here.
 */
import type { DocumentKind } from '../../domain/reviewCard';

/** `subject` → `attribute` → his own plain words for the line. */
const FIELD_LABELS: Record<string, Record<string, string>> = {
  lipid_panel: {
    total_cholesterol: 'The total cholesterol',
    hdl: 'The good cholesterol',
    ldl: 'The bad cholesterol',
    ldl_reference_range: 'The normal range for the bad cholesterol',
    triglycerides: 'The blood fats',
    vldl: 'Another blood fat number',
    tc_hdl_ratio: 'The cholesterol ratio',
    non_hdl_cholesterol: 'The cholesterol without the good part',
  },
  blood_test: {
    hba1c: 'Your sugar test',
    haemoglobin: 'Your blood count',
    tsh: 'Your thyroid test',
    uric_acid: 'Your uric acid number',
    white_cells: 'Your white blood cell number',
    platelets: 'Your platelet number',
  },
  kidney_panel: {
    creatinine: 'Your kidney number',
    egfr: 'Your kidney filter',
    potassium: 'Your body salt',
    urea: 'The waste number from your kidneys',
    sodium: 'The salt number in your blood',
  },
  liver_panel: {
    alt: 'One of your liver numbers',
    ast: 'Another of your liver numbers',
    alp: 'A liver and bone number',
    ggt: 'A liver and alcohol number',
    bilirubin: 'The yellow colour number',
    albumin: 'The protein number in your blood',
  },
  full_blood_count: { hemoglobin: 'The blood count number' },
  device: { kind: 'The machine' },
  blood_pressure: { systolic: 'The top number', diastolic: 'The bottom number' },
  heart_rate: { pulse: 'The heartbeat' },
  reading: { taken_at: 'When it was taken' },
  visit: { doctor: 'The doctor', next_visit: 'The next visit' },
  discharge: {
    admitted_on: 'When you went in',
    discharged_on: 'When you came home',
    reason: 'Why you were in hospital',
    weight_at_discharge: 'Your weight when you came home',
  },
  follow_up: { date: 'When to go back' },
  hypertension: { control: 'What the doctor wrote about your blood pressure' },
  blood_sugar: { glucose: 'The sugar number' },
  lab_report: {
    lab: 'Where the blood was tested',
    facility: 'Where it was tested',
    remark: 'What the report says beside the numbers',
    patient_name: 'The name on the report',
    patient_id: 'The patient number on the report',
    ordering_doctor: 'Which doctor asked for it',
  },
  person: { birth_year: 'The year of birth', age: 'The age on the report', sex: 'Male or female' },
  medicine: {
    name: 'The medicine',
    strength: 'How strong it is',
    dose: 'How to take it',
    frequency: 'How often to take it',
    quantity: 'How many were given',
    dispensed_at: 'When it was given',
    prescriber: 'Which doctor wrote it',
  },
  insurance_policy: {
    insurer: 'The insurance company',
    policy_number: 'The policy number',
    plan: 'The plan',
    holder: 'Who the policy is for',
    start_date: 'When it started',
    end_date: 'When it ends',
    waiting_period: 'The waiting period',
    claims_contact: 'Who to contact for a claim',
    covers: 'What it covers',
    excludes: 'What it does not cover',
    benefit: 'A benefit or a limit',
    claim_step: 'A step to claim',
  },
  insurance_claim: {
    insurer: 'The insurance company',
    claim_number: 'The claim number',
    status: 'Where the claim stands',
    amount: 'The amount',
    date: 'The date',
    for: 'What the claim was for',
  },
  pill: {
    imprint: 'What is printed on it',
    colour: 'Its colour',
    shape: 'Its shape',
    score_line: 'Whether it can be split',
  },
  receipt: { pharmacy: 'The pharmacy', currency: 'The currency' },
  item: { name: 'What was bought', quantity: 'How many', unit_price: 'The price each', total: 'The total price' },
};

const OTHER_LINE = 'Another line on the paper';

const ITEM_SUBJECT = /^item_\d+$/;
const ESSENTIAL_ATTRIBUTE = /^(covers|excludes|benefit|claim_step)_\d+$/;

/**
 * His words for the line: the canonical label for the backend's
 * subject/attribute when known; failing that, the paper's own printed
 * words (`labelOnPaper`); only when neither exists, a generic line
 * name. Never the bare subject/attribute code either way.
 */
export function fieldLabel(field: { subject: string; attribute: string; labelOnPaper: string | null }): string {
  const subject = ITEM_SUBJECT.test(field.subject) ? 'item' : field.subject;
  const essential = field.subject === 'insurance_policy' ? field.attribute.match(ESSENTIAL_ATTRIBUTE) : null;
  const attribute = essential ? essential[1] : field.attribute;
  const known = FIELD_LABELS[subject]?.[attribute];
  if (known) return known;
  const printed = field.labelOnPaper?.trim();
  return printed && printed.length > 0 ? printed : OTHER_LINE;
}

/**
 * Whether a row is a measured result (a unit or a printed range to
 * place it against) rather than an administrative line (a name, a
 * date, a facility). The report table's own split — a result row never
 * shows its subject/attribute token; an admin row shows its plain
 * label and nothing else numeric.
 */
export function isResultRow(field: { unit: string | null; range: { low: number | null; high: number | null; text: string | null } | null }): boolean {
  return field.unit != null || (field.range != null && (field.range.low != null || field.range.high != null || field.range.text != null));
}

/** The report table's own short title for the kind of paper — a name, never a sentence. */
export function kindTitle(kind: DocumentKind): string {
  switch (kind) {
    case 'lab_report':
      return 'Blood test';
    case 'medicine_label':
      return 'Medicine label';
    case 'discharge_letter':
      return 'Hospital letter';
    case 'clinic_slip':
      return 'Appointment card';
    case 'handwritten_prescription':
      return "Doctor's note";
    case 'insurance_letter':
      return 'Insurance letter';
    case 'insurance_policy':
      return 'Insurance policy';
    case 'insurance_claim':
      return 'Insurance claim';
    case 'device_screen':
      return 'Machine screen';
    case 'pill_photo':
      return 'Pill photo';
    case 'pharmacy_receipt':
      return 'Pharmacy receipt';
    case 'other':
      return 'Health paper';
    case 'not_health':
    case 'unknown':
    case 'unsupported_file_type':
      return 'Page';
  }
}
