/**
 * The whose-paper question's sentence, composed client-side from the
 * closed `mismatched` field list the backend sends (`domain/reviewCard.ts`'s
 * `ReviewClarify`) — never the paper's own printed value (the independent
 * safety review's fix, `ReviewClarifyOut`'s own doc). Mirrors
 * `web/src/strings/en.ts`'s `whose*` keys exactly, so the two clients say
 * the same sentence.
 */
const FIELD_WORD: Record<string, string> = {
  name: 'the name',
  patient_id: 'the patient number',
  birth_year: 'the year of birth',
  sex: 'the sex',
};

function joinFields(fields: string[]): string {
  const words = fields.map((f) => FIELD_WORD[f] ?? f);
  if (words.length === 0) return "This paper's details";
  const joined = words.length === 1 ? words[0] : words.slice(0, -1).join(', ') + ' and ' + words[words.length - 1];
  return joined[0].toUpperCase() + joined.slice(1);
}

export function whoseMismatchLead(fields: string[]): string {
  if (fields.length === 0) return 'This paper’s details do not match your own.';
  const lead = joinFields(fields);
  const verb = fields.length > 1 ? 'are' : 'is';
  return `${lead} on this paper ${verb} not yours.`;
}

export const whoseQuestion = 'Is it yours?';
export const whoseChips = [
  { label: 'Yes, it is mine', value: 'mine' },
  { label: 'No, it is someone else’s', value: 'someone_elses' },
  { label: 'I’m not sure', value: null },
] as const;

export function duplicateLead(addedOn: string | null): string {
  return addedOn
    ? `This looks like the paper you added on ${addedOn}.`
    : 'This looks like a paper you already have.';
}

export const duplicateQuestion = 'Is it the same one?';
export const duplicateChips = [
  { label: 'Yes, it’s the same paper', value: 'same' },
  { label: 'No, a different one', value: 'different' },
] as const;
