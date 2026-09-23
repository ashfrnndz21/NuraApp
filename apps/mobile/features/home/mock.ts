/**
 * Realistic Home data (spec §29 — never lorem ipsum), matching Tan's
 * vocabulary in `docs/design/experience-blueprint-v2.html` (`V_TAN`).
 * This is what `lib/api`'s stub client returns until the real routes
 * (`backend/app/channels/api`) are wired — the swap is a config flip.
 */
import type { AskFixtureAnswer } from '../../lib/ai/events';

export const tan = {
  who: 'Tan',
  initial: 'T',
  greeting: 'Good evening, Tan',
  prompt: 'How are you today?',
};

export const homeHeadline = 'Four numbers to raise with your *doctor.*';

export const healthInsight = {
  title: 'Your health',
  date: { day: '12', month: 'Sep' },
  body: 'Your blood test has four numbers outside the range printed on the paper. Your three questions are kept for Dr Lim.',
  cta: 'See them in a table',
};

export const bloodTest = {
  title: 'Blood test',
  subtitle: '12 September · 5 results · 4 outside',
  cta: 'Look',
};

export const eveningReminder = {
  label: 'Evening tablet due at 9 pm',
  medicine: 'Atorvastatin 20 mg',
};

export const bloodPressureVideo = {
  title: 'Your blood pressure tablet, in 30 seconds',
  why: 'Because you take amlodipine',
  publisher: 'National Heart Centre',
  duration: '0:32',
};

export const bloodPressureExpand = {
  possessive: 'your',
  explain: 'Five of the last seven mornings sat above your usual band. The reading was taken before your tablet on four of them.',
};

export const askFixtureAnswer: AskFixtureAnswer = {
  question: 'How has my blood pressure been?',
  stage: 'Looking at your last seven mornings',
  contextFirst: 'Your blood pressure has been slightly higher than usual this week.',
  followUp: 'Would you like me to explain what changed?',
  explain: 'Your dose changed on 9 September, and four of the five high mornings were before you took it. That is worth raising with Dr Lim on the 25th.',
  chips: ['Explain', 'Show my readings', 'Ask something else'],
} as const;

export const medicines = {
  amlodipine: { plain: 'Blood pressure tablet', real: 'Amlodipine 10 mg · one each morning', prescriber: 'Dr Lim · changed from 5 mg on 9 September' },
  atorvastatin: { plain: 'Cholesterol tablet', real: 'Atorvastatin 20 mg · one at night', prescriber: 'Dr Lim · since June 2024' },
};
