import type { ConditionWordOut } from "../types";

/** The condition graph the mock answers `GET /onboarding/conditions` with: the words of
 *  docs/onboarding.html, plain word first, sized by how common each is. The real graph is
 *  E01's and lives in the backend; this one exists so the cloud can be built and tested
 *  before that lands. English only — the backend owns the words in three languages.
 *
 *  Only the plain words and the follow-up questions are patient lines, tagged for
 *  `npm run plain-words`. The clinic's terms are not lines: each fills the slot in
 *  "Doctors call it {term}." (the catalogue's line, which is verified), the way a
 *  drug's name fills a slot in a backend sentence. They sit apart, untagged, in TERMS. */

type Ask = { q: string; o: [string, string][] };
type Word = [id: string, word: string, weight: 1 | 2 | 3, related?: string[], ask?: Ask];

// @patient phrase
const TOP: Word[] = [
  ["bp", "High blood pressure", 3, ["bp_meds", "bp_home", "ankles", "kidney_chk", "heart_doc", "stroke_fam"]],
  ["chol", "Cholesterol", 3, ["statin", "muscle", "heart_doc", "liver"]],
  ["sugar", "Sugar, diabetes", 3, ["sugar_tabs", "insulin", "sugar_home", "feet", "eyes_yr", "kidney_chk"]],
  ["heart", "Heart", 3, ["hf", "stent", "afib", "breathless", "thinner", "heart_doc"]],
  ["kidney", "Kidneys", 2, ["kidney_chk", "swelling", "dialysis"]],
  ["breath", "Asthma, breathing", 2, ["inhaler", "lungs", "snore"]],
  ["joints", "Joints, arthritis", 2, ["knee", "painkill", "falls"]],
  ["stomach", "Stomach, reflux", 2, ["reflux_tabs", "ulcer"]],
  ["sleep", "Sleep", 2, ["snore", "sleep_tabs"]],
  ["weight", "Weight", 2, ["weight_jab", "diet"]],
  ["allergy", "Allergies", 2, ["drug_all", "food_all"]],
  ["hosp", "In hospital last year", 2, ["dl_have"]],
  ["meds5", "5 or more medicines", 2, ["bag"]],
  ["famhx", "Family history", 2, ["stroke_fam", "heart_fam", "sugar_fam", "cancer_fam"]],
  ["thyroid", "Thyroid", 1, ["thy_tabs"]],
  ["cancer", "Cancer, now or before", 1, ["cancer_tx", "cancer_checks"]],
  ["stroke", "A stroke or a small stroke", 1, ["thinner", "stroke_fam"]],
  ["eyes", "Eyes", 1, ["cataract", "eyes_yr"]],
  ["smoke", "Smoking", 1, ["quit"]],
  ["memory", "Memory", 1, ["mem_doc", "mem_worry"]],
];

// @patient phrase
const NEXT: Word[] = [
  ["bp_meds", "On tablets for it", 2, undefined, { q: "How long have you taken them?", o: [["lt1", "Under a year"], ["1to5", "1 to 5 years"], ["gt5", "More than 5 years"]] }],
  ["bp_home", "I check it at home", 1, undefined, { q: "What is your top number usually?", o: [["lt130", "Under 130"], ["130to150", "130 to 150"], ["gt150", "Over 150"], ["unsure", "I am not sure"]] }],
  ["ankles", "Swollen ankles", 1],
  ["kidney_chk", "My kidney number is watched", 1],
  ["heart_doc", "I see a heart doctor", 1, undefined, { q: "How often do you see the heart doctor?", o: [["3m", "Every 3 months"], ["6m", "Every 6 months"], ["1y", "Every year"], ["need", "Only when I need to"]] }],
  ["stroke_fam", "A stroke in the family", 1],
  ["statin", "The cholesterol tablet", 2, undefined, { q: "Does the tablet trouble you?", o: [["none", "It does not"], ["aches", "My muscles ache"], ["unsure", "I am not sure"]] }],
  ["muscle", "Aching muscles", 1],
  ["liver", "Fatty liver", 1],
  ["sugar_tabs", "The sugar tablet", 2],
  ["insulin", "Insulin", 2, undefined, { q: "How many times a day do you take it?", o: [["1", "Once a day"], ["2", "Twice a day"], ["more", "More than twice"]] }],
  ["sugar_home", "I check my sugar at home", 1],
  ["feet", "Numb feet", 1],
  ["eyes_yr", "An eye check every year", 1],
  ["hf", "A weak heart", 2, ["water_pill", "weigh"]],
  ["stent", "A stent or a bypass", 2, undefined, { q: "When did you have it?", o: [["ty", "This year"], ["1to5", "1 to 5 years ago"], ["longer", "Longer ago"]] }],
  ["afib", "An uneven heartbeat", 2, ["thinner"]],
  ["breathless", "Out of breath on the stairs", 1],
  ["thinner", "A blood thinner", 2, undefined, { q: "Which kind do you take?", o: [["warfarin", "Warfarin, with blood tests"], ["newer", "A newer one, with no tests"], ["unsure", "I am not sure"]] }],
  ["water_pill", "The water pill", 1],
  ["weigh", "I weigh myself", 1],
  ["swelling", "Swollen legs", 1],
  ["dialysis", "Dialysis", 2],
  ["inhaler", "I use an inhaler", 1],
  ["lungs", "Weak lungs", 1],
  ["snore", "I snore or stop breathing at night", 1],
  ["knee", "Knees", 1],
  ["painkill", "Pain tablets most days", 1],
  ["falls", "A fall this year", 2],
  ["thy_tabs", "The thyroid tablet", 1],
  ["reflux_tabs", "The reflux tablet", 1],
  ["ulcer", "A stomach ulcer before", 1],
  ["sleep_tabs", "Sleeping tablets", 1],
  ["weight_jab", "A weight injection", 1],
  ["diet", "Trying to lose weight", 1],
  ["cancer_tx", "In treatment now", 2],
  ["cancer_checks", "Check-ups only", 1],
  ["cataract", "Cloudy eyes", 1],
  ["drug_all", "Allergic to a medicine", 2, undefined, { q: "Which medicine is it?", o: [["penicillin", "One for infections"], ["aspirin", "Aspirin"], ["another", "Another one"], ["unsure", "I am not sure"]] }],
  ["food_all", "A food allergy", 1],
  ["quit", "I stopped smoking", 1],
  ["dl_have", "I have the hospital letter", 1],
  ["bag", "I can take a photo of the medicine bag", 1],
  ["heart_fam", "Heart trouble in the family", 1],
  ["sugar_fam", "Diabetes in the family", 1],
  ["cancer_fam", "Cancer in the family", 1],
  ["mem_doc", "I saw a doctor about it", 1],
  ["mem_worry", "My family is worried", 1],
];

/** The clinic's word for each, shown in brackets after the plain word and spoken as
 *  "Doctors call it …". Slot values, not lines; see the note at the top. */
const TERMS: Record<string, string> = {
  bp: "hypertension",
  chol: "hyperlipidaemia",
  sugar: "diabetes mellitus",
  heart: "heart disease",
  kidney: "chronic kidney disease",
  breath: "asthma",
  joints: "osteoarthritis",
  stomach: "reflux disease",
  sleep: "insomnia",
  weight: "obesity",
  allergy: "allergy",
  hosp: "hospital admission",
  meds5: "polypharmacy",
  thyroid: "thyroid disease",
  stroke: "stroke or TIA",
  ankles: "oedema",
  heart_doc: "cardiologist",
  statin: "statin",
  muscle: "myalgia",
  liver: "hepatic steatosis",
  sugar_tabs: "metformin and others",
  feet: "neuropathy",
  hf: "heart failure",
  afib: "atrial fibrillation",
  thinner: "anticoagulant",
  water_pill: "diuretic",
  swelling: "oedema",
  lungs: "COPD",
  snore: "sleep apnoea",
  painkill: "analgesics",
  thy_tabs: "levothyroxine",
  reflux_tabs: "proton pump inhibitor",
  ulcer: "peptic ulcer",
  sleep_tabs: "hypnotics",
  weight_jab: "GLP-1 injection",
  cataract: "cataract",
  drug_all: "drug allergy",
  dl_have: "discharge summary",
};

function parents(): Map<string, string> {
  const found = new Map<string, string>();
  for (const [id, , , related] of [...TOP, ...NEXT]) for (const each of related ?? []) if (!found.has(each)) found.set(each, id);
  return found;
}

export function conditionWords(): ConditionWordOut[] {
  const parentOf = parents();
  return [...TOP, ...NEXT].map(([id, word, weight, related, ask]) => ({
    id,
    word,
    term: TERMS[id] ?? null,
    weight,
    parent: parentOf.get(id) ?? null,
    related: related ?? [],
    ask: ask ? { question: ask.q, options: ask.o.map(([option, text]) => ({ id: option, text })) } : null,
  }));
}

export const wordById = (id: string): ConditionWordOut | undefined => conditionWords().find((each) => each.id === id);
